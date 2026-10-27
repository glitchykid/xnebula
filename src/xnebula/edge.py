"""Signed Edge uninstall with an explicitly scoped force-delete fallback."""

import json
from dataclasses import dataclass

from xnebula.services import payload
from xnebula.windows import BackendError, WindowsBackend

EDGE_ROOTS = r"""
$roots = @()
if (${env:ProgramFiles(x86)}) {
    $roots += (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application')
}
if ($env:ProgramFiles) { $roots += (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application') }
if ($env:LocalAppData) { $roots += (Join-Path $env:LocalAppData 'Microsoft\Edge\Application') }
$roots = @($roots | Select-Object -Unique)
"""


@dataclass(frozen=True)
class EdgeInstallation:
    executable: str
    installer: str
    system: bool


class WindowsEdge:
    def __init__(self, *, bridge=None):
        self.bridge = bridge if bridge is not None else WindowsBackend()

    def inventory(self):
        script = (
            EDGE_ROOTS
            + r"""
$rows = @(foreach ($root in $roots) {
    $executable = Join-Path $root 'msedge.exe'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { continue }
    $versions = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop |
        Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
        Sort-Object { [version]$_.Name } -Descending)
    $setup = ''
    foreach ($version in $versions) {
        $candidate = Join-Path $version.FullName 'Installer\setup.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $setup = $candidate; break }
    }
    [PSCustomObject]@{executable=$executable; installer=$setup
        system= -not $root.StartsWith($env:LocalAppData + '\',
            [StringComparison]::OrdinalIgnoreCase)}
})
ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
"""
        )
        try:
            rows = json.loads(self.bridge._run(script))
            if not isinstance(rows, list):
                raise ValueError
            result = []
            for row in rows:
                item = EdgeInstallation(**row)
                if (
                    not isinstance(item.executable, str)
                    or not item.executable
                    or not isinstance(item.installer, str)
                    or type(item.system) is not bool
                ):
                    raise ValueError
                result.append(item)
            return result
        except (TypeError, ValueError) as error:
            raise BackendError("Windows returned an invalid Microsoft Edge inventory.") from error

    def remove(self, item):
        script = (
            payload(
                {"executable": item.executable, "installer": item.installer, "system": item.system}
            )
            + EDGE_ROOTS
            + r"""
$root = [IO.Path]::GetFullPath((Split-Path $target.executable -Parent))
if ($roots -notcontains $root -or (Split-Path $target.executable -Leaf) -ne 'msedge.exe') {
    throw 'Unexpected Microsoft Edge installation path.'
}
$system = -not $root.StartsWith($env:LocalAppData + '\', [StringComparison]::OrdinalIgnoreCase)
if ($target.system -ne $system) { throw 'Edge installation scope changed. Preview again.' }
$signature = Get-AuthenticodeSignature -LiteralPath $target.executable -ErrorAction Stop
if ($signature.Status -ne 'Valid' -or
    $signature.SignerCertificate.Subject -notmatch '^CN=Microsoft Corporation(?:,|$)') {
    throw 'The Edge browser does not have a valid Microsoft signature.'
}
if ($target.installer) {
    $setup = [IO.Path]::GetFullPath($target.installer)
    $expectedRoot = Split-Path (Split-Path (Split-Path $setup -Parent) -Parent) -Parent
    $version = Split-Path (Split-Path (Split-Path $setup -Parent) -Parent) -Leaf
    if ($expectedRoot -ne $root -or $version -notmatch '^\d+\.\d+\.\d+\.\d+$' -or
        (Split-Path $setup -Leaf) -ne 'setup.exe' -or
        (Split-Path (Split-Path $setup -Parent) -Leaf) -ne 'Installer') {
        throw 'Unexpected Edge uninstaller path.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $setup -ErrorAction Stop
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Subject -notmatch '^CN=Microsoft Corporation(?:,|$)') {
        throw 'The Edge uninstaller does not have a valid Microsoft signature.'
    }
}
foreach ($process in @(Get-Process -Name msedge -ErrorAction SilentlyContinue)) {
    if ($process.Path -eq $target.executable) {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
    }
}
if ($target.installer) {
    $arguments = @('--uninstall', '--force-uninstall', '--verbose-logging')
    if ($target.system) { $arguments += '--system-level' }
    try {
        $result = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru `
            -WindowStyle Hidden
    } catch { }
}
if (-not (Test-Path -LiteralPath $target.executable -PathType Leaf)) {
    'uninstalled'
} else {
    # Refuse links before recursive ownership/deletion could leave the validated Edge root.
    $cursor = $root
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Edge path contains a junction or symbolic link. Force deletion was refused.'
        }
        $parent = Split-Path $cursor -Parent
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    $pending = New-Object 'Collections.Generic.Queue[string]'
    $pending.Enqueue($root)
    while ($pending.Count -gt 0) {
        $directory = $pending.Dequeue()
        foreach ($child in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Edge contains linked files. Force deletion was refused.'
            }
            if ($child.PSIsContainer) { $pending.Enqueue($child.FullName) }
        }
    }
    & ($env:SystemRoot + '\System32\takeown.exe') /f $root /a /r /d Y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not obtain access to the Edge installation folder.' }
    & ($env:SystemRoot + '\System32\icacls.exe') $root /grant '*S-1-5-32-544:(OI)(CI)F' /t |
        Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not grant deletion access to Edge files.' }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $root) { throw 'Some Edge files remain. Removal was not confirmed.' }
    'force-deleted'
}
"""
        )
        result = self.bridge._run(script)
        if result not in ("uninstalled", "force-deleted"):
            raise BackendError(
                "Microsoft Edge removal was not confirmed. Check Windows before retrying."
            )
        return result
