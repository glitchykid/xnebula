"""Native Windows PowerShell bridge. No shell interpolation of user input."""

import base64
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

from xnebula.core import Package, removable_name


class BackendError(RuntimeError):
    """A Windows operation failed or could not be verified."""


INVENTORY = r"""
$allPackages = @(Get-AppxPackage -AllUsers -PackageTypeFilter Bundle,Main,Framework,Resource `
    -ErrorAction Stop)
$packages = @($allPackages | Where-Object { -not $_.IsFramework -and -not $_.IsResourcePackage })
$protectedNames = @($allPackages | Where-Object {
    $_.IsFramework -or ($_.NonRemovable -and -not $_.IsResourcePackage) -or
    $_.InstallLocation -like ($env:SystemRoot + '\SystemApps\*')
} | ForEach-Object { $_.Name })
$microsoftPublishers = @('8wekyb3d8bbwe', 'cw5n1h2txyewy', '8xb3b82q0j6ny') + @(
    $packages | Where-Object { $_.Publisher -match '^CN=Microsoft (Corporation|Windows)' } |
    ForEach-Object { $_.PublisherId }
)
$bundles = @($packages | Where-Object { $_.IsBundle } |
    ForEach-Object { $_.Name + '|' + $_.Version + '|' + $_.PublisherId })
$rows = @(
    foreach ($p in $packages) {
        $identity = $p.Name + '|' + $p.Version + '|' + $p.PublisherId
        if (-not $p.IsBundle -and $bundles -contains $identity) { continue }
        [PSCustomObject]@{
            name = $p.Name; full_name = $p.PackageFullName; kind = 'installed'
            protected = [bool](($protectedNames -contains $p.Name) -or
                ($p.Publisher -notmatch '^CN=Microsoft (Corporation|Windows)'))
        }
    }
    foreach ($p in @(Get-AppxProvisionedPackage -Online -ErrorAction Stop)) {
        [PSCustomObject]@{
            name = $p.DisplayName; full_name = $p.PackageName
            kind = 'provisioned'
            protected = [bool](($protectedNames -contains $p.DisplayName) -or
                ($microsoftPublishers -notcontains ($p.PackageName -split '_')[-1]))
        }
    }
)
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""


def parse_inventory(payload: str) -> list[Package]:
    try:
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise ValueError
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            if any(
                not isinstance(row.get(key), str) or not row[key].strip()
                for key in ("name", "full_name")
            ):
                raise ValueError
            if (
                row.get("kind") not in ("installed", "provisioned")
                or type(row.get("protected")) is not bool
            ):
                raise ValueError
            result.append(Package(row["name"], row["full_name"], row["kind"], row["protected"]))
        return result
    except (ValueError, TypeError) as error:
        raise BackendError(
            "Windows returned invalid inventory data; no removal plan can be trusted."
        ) from error


def removal_script(item: Package) -> str:
    if item.protected or not removable_name(item.name):
        raise BackendError("Refusing to remove a protected or unlisted package.")
    if item.kind not in ("installed", "provisioned") or not item.full_name:
        raise BackendError("Invalid package identity.")
    # A JSON payload is encoded as data, never treated as PowerShell source.
    payload = base64.b64encode(
        json.dumps({"name": item.name, "full": item.full_name}).encode()
    ).decode()
    prelude = (
        "$target = [Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{payload}')) | ConvertFrom-Json\n"
    )
    if item.kind == "installed":
        return (
            prelude
            + r"""
$p = @(Get-AppxPackage -AllUsers -PackageTypeFilter Bundle,Main -ErrorAction Stop |
    Where-Object { $_.PackageFullName -eq $target.full -and $_.Name -eq $target.name })
if ($p.Count -eq 0) { throw 'Package changed since preview. Scan again.' }
foreach ($match in $p) {
    if ($match.NonRemovable -or $match.IsFramework -or $match.IsResourcePackage -or
        $match.InstallLocation -like ($env:SystemRoot + '\SystemApps\*') -or
        $match.Publisher -notmatch '^CN=Microsoft (Corporation|Windows)') {
        throw 'Package is protected. No removal attempted.'
    }
}
$locations = @($p | Where-Object { $_.InstallLocation } |
    ForEach-Object { $_.InstallLocation.TrimEnd('\') + '\' })
if ($locations.Count -gt 0) {
    foreach ($process in @(Get-Process -ErrorAction SilentlyContinue)) {
        try { $executable = $process.Path } catch { continue }
        if (-not $executable) { continue }
        foreach ($location in $locations) {
            if ($executable.StartsWith($location, [StringComparison]::OrdinalIgnoreCase)) {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
                break
            }
        }
    }
}
Remove-AppxPackage -Package $target.full -AllUsers -Confirm:$false -ErrorAction Stop
$remaining = @(Get-AppxPackage -AllUsers -PackageTypeFilter Bundle,Main -ErrorAction Stop |
    Where-Object { $_.PackageFullName -eq $target.full })
if ($remaining.Count -ne 0) {
    throw 'Package remains registered or staged. Scan again after reboot.'
}
'ok'
"""
        )
    return (
        prelude
        + r"""
$p = @(Get-AppxProvisionedPackage -Online -ErrorAction Stop |
    Where-Object { $_.PackageName -eq $target.full -and $_.DisplayName -eq $target.name })
if ($p.Count -eq 0) { throw 'Provisioning changed since preview. Scan again.' }
$result = Remove-AppxProvisionedPackage -Online -PackageName $target.full -ErrorAction Stop
if ($result.RestartNeeded) { throw 'Windows requested a restart. Reboot, then scan again.' }
$remaining = @(Get-AppxProvisionedPackage -Online -ErrorAction Stop |
    Where-Object { $_.PackageName -eq $target.full })
if ($remaining.Count -ne 0) { throw 'Package remains provisioned. Scan again.' }
'ok'
"""
    )


class WindowsBackend:
    def __init__(self):
        if sys.platform != "win32":
            raise BackendError("System-wide scanning and removal require Windows 11.")
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise BackendError(
                "Open PowerShell with 'Run as administrator' for system-wide scanning and removal."
            )
        if sys.getwindowsversion().build < 22000:
            raise BackendError("XNebula supports Windows 11 (build 22000 or newer).")
        system = "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"
        self.executable = (
            Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
            / system
            / "WindowsPowerShell/v1.0/powershell.exe"
        )
        if not self.executable.is_file():
            raise BackendError("Built-in Windows PowerShell could not be found.")

    def _run(self, script: str) -> str:
        wrapped = (
            "$ErrorActionPreference = 'Stop'\n"
            "$ProgressPreference = 'SilentlyContinue'\n"
            "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
            "try {\n"
            + script
            + "\n} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
        )
        encoded = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
        try:
            result = subprocess.run(
                [
                    str(self.executable),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded,
                ],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise BackendError(
                "PowerShell timed out. Windows may still be processing; scan again before retrying."
            ) from error
        except OSError as error:
            raise BackendError(f"Could not start Windows PowerShell: {error}") from error
        if result.returncode:
            raise BackendError(
                result.stderr.strip() or f"PowerShell exited with code {result.returncode}."
            )
        return result.stdout.strip().lstrip("\ufeff")

    def inventory(self) -> list[Package]:
        return parse_inventory(self._run(INVENTORY))

    def remove(self, item: Package) -> None:
        if self._run(removal_script(item)) != "ok":
            raise BackendError("Windows did not confirm removal. Scan again before retrying.")
