# Windows PowerShell 5.1 launcher for the portable release and developer venv.
param(
    [switch]$Elevate,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArguments
)

function New-XNebulaElevationCommand {
    param([string]$ScriptPath, [string[]]$AppArguments)
    $forwardArguments = @()
    if ($AppArguments) { $forwardArguments = @($AppArguments) }
    $payload = @{ Script = $ScriptPath; Arguments = $forwardArguments } | ConvertTo-Json -Compress
    $encodedData = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    $command = '$ErrorActionPreference = ''Stop''; $data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(''' + $encodedData + ''')) | ConvertFrom-Json; $forward = @($data.Arguments); & $data.Script @forward; exit $LASTEXITCODE'
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

# Dot-sourcing exposes only the argument encoder for automated launcher tests.
if ($MyInvocation.InvocationName -eq '.') { return }

$ErrorActionPreference = 'Stop'
try {
    # Apply the black palette to this console session, including the elevated host.
    if (-not [Console]::IsOutputRedirected) {
        try {
            $Host.UI.RawUI.BackgroundColor = 'Black'
            $Host.UI.RawUI.ForegroundColor = 'Gray'
            [Console]::BackgroundColor = [ConsoleColor]::Black
            [Console]::ForegroundColor = [ConsoleColor]::Gray
            [Console]::Clear()
            $Host.PrivateData.ErrorBackgroundColor = 'Black'
            $Host.PrivateData.WarningBackgroundColor = 'Black'
        } catch { }
    }
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    if ($Elevate) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            # Keep paths and arguments as encoded data through the UAC boundary.
            $encodedCommand = New-XNebulaElevationCommand -ScriptPath $PSCommandPath -AppArguments $AppArguments
            $hostPath = Join-Path $PSHOME 'powershell.exe'
            # This is the interactive terminal the user explicitly requested.
            $process = Start-Process -FilePath $hostPath -Verb RunAs -Wait -PassThru -WindowStyle Normal -WorkingDirectory $root -ArgumentList @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encodedCommand)
            exit $process.ExitCode
        }
    }
    $python = Join-Path $root '.runtime\python.exe'
    if (-not [IO.File]::Exists($python)) {
        $python = Join-Path $root '.venv\Scripts\python.exe'
    }
    if (-not [IO.File]::Exists($python)) {
        throw 'Python runtime is missing. Extract the complete windows-x64 ZIP from https://github.com/glitchykid/xnebula/releases/latest, then open Start-XNebula.cmd. Developers can install into .venv as described in README.md.'
    }
    # Keep reports/backups next to the extracted app, regardless of caller location.
    Set-Location -LiteralPath $root
    if (-not $AppArguments -or $AppArguments.Count -eq 0) {
        $AppArguments = @('menu')
    }
    & $python -m xnebula @AppArguments
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('XNebula could not start: ' + $_.Exception.Message)
    exit 1
}
