import base64
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from xnebula.core import Package
from xnebula.windows import INVENTORY, BackendError, WindowsBackend, removal_script

NEWS = Package("Microsoft.BingNews", "Microsoft.BingNews_1_x64__publisher", "installed")


def bridge():
    backend = WindowsBackend.__new__(WindowsBackend)
    backend.executable = (
        Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    return backend


class BridgeTests(unittest.TestCase):
    def test_non_windows_is_rejected(self):
        with patch("sys.platform", "linux"), self.assertRaisesRegex(BackendError, "Windows"):
            WindowsBackend()

    @unittest.skipUnless(sys.platform == "win32", "Windows platform checks")
    def test_non_admin_is_rejected(self):
        with (
            patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0),
            self.assertRaisesRegex(BackendError, "administrator"),
        ):
            WindowsBackend()

    @unittest.skipUnless(sys.platform == "win32", "Windows platform checks")
    def test_supported_and_unsupported_windows_builds(self):
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1):
            with (
                patch("sys.getwindowsversion", return_value=SimpleNamespace(build=19045)),
                self.assertRaisesRegex(BackendError, "Windows 11"),
            ):
                WindowsBackend()
            with (
                patch("pathlib.Path.is_file", return_value=False),
                self.assertRaisesRegex(BackendError, "could not be found"),
            ):
                WindowsBackend()
            self.assertTrue(WindowsBackend().executable.is_file())

    def test_process_uses_encoded_command_without_shell_or_profile(self):
        with patch(
            "subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="\ufeffok\n", stderr=""),
        ) as run:
            self.assertEqual(bridge()._run("'ok'"), "ok")
            args, kwargs = run.call_args
            self.assertIn("-NoProfile", args[0])
            self.assertNotIn("shell", kwargs)
            self.assertIn("'ok'", base64.b64decode(args[0][-1]).decode("utf-16-le"))
            self.assertEqual(kwargs["timeout"], 300)

    def test_process_errors_are_actionable(self):
        for error in (OSError("missing"), subprocess.TimeoutExpired("powershell", 300)):
            with (
                self.subTest(error=error),
                patch("subprocess.run", side_effect=error),
                self.assertRaises(BackendError),
            ):
                bridge()._run("'ok'")
        for stderr in ("Access denied", ""):
            with (
                patch(
                    "subprocess.run",
                    return_value=SimpleNamespace(returncode=1, stdout="", stderr=stderr),
                ),
                self.assertRaises(BackendError),
            ):
                bridge()._run("'ok'")

    def test_inventory_and_removal_require_valid_responses(self):
        backend = bridge()
        with patch.object(backend, "_run", return_value="[]"):
            self.assertEqual(backend.inventory(), [])
            with self.assertRaises(BackendError):
                backend.remove(NEWS)
        with patch.object(backend, "_run", return_value="ok"):
            backend.remove(NEWS)

    def test_unknown_protected_or_invalid_targets_cannot_produce_a_script(self):
        for item in (
            Package("Microsoft.SecHealthUI", "security_1", "installed"),
            Package(NEWS.name, NEWS.full_name, "installed", True),
            Package(NEWS.name, "", "installed"),
            Package(NEWS.name, NEWS.full_name, "bad"),
        ):
            with self.subTest(item=item), self.assertRaises(BackendError):
                removal_script(item)

    def test_package_identity_is_encoded_as_data(self):
        malicious = "'; throw 'injected'; #"
        self.assertNotIn(malicious, removal_script(Package(NEWS.name, malicious, "installed")))


# These functions shadow native cmdlets in a child PowerShell process. No real
# package is queried or removed. Parameter assertions exercise the production scripts.
STUBS = r"""
$script:removed = $false
$script:provisionRemoved = $false
$script:protected = $false
$script:keep = $false
$script:restart = $false
function Get-AppxPackage {
    param([switch]$AllUsers, $PackageTypeFilter, $ErrorAction)
    if (-not $AllUsers -or $PackageTypeFilter -notcontains 'Bundle') { throw 'Wrong scope' }
    if (-not $script:removed -or $script:keep) {
        [PSCustomObject]@{Name='Microsoft.BingNews'; Version='1.0';
            PackageFullName='Microsoft.BingNews_1_x64__publisher'; IsBundle=$true;
            Publisher='CN=Microsoft Corporation'; PublisherId='publisher';
            NonRemovable=$script:protected; IsFramework=$false; IsResourcePackage=$false}
        [PSCustomObject]@{Name='Microsoft.BingNews'; PackageFullName='child';
            Version='1.0'; IsBundle=$false; NonRemovable=$false;
            Publisher='CN=Microsoft Corporation'; PublisherId='publisher';
            IsFramework=$false; IsResourcePackage=$false}
    }
}
function Get-AppxProvisionedPackage {
    param([switch]$Online, $ErrorAction)
    if (-not $Online) { throw 'Wrong image' }
    if (-not $script:provisionRemoved -or $script:keep) {
        [PSCustomObject]@{DisplayName='Microsoft.BingNews';
            PackageName='Microsoft.BingNews_1_x64__publisher'}
    }
}
function Remove-AppxPackage {
    param($Package, [switch]$AllUsers, $Confirm, $ErrorAction)
    if (-not $AllUsers -or $Package -ne 'Microsoft.BingNews_1_x64__publisher') {
        throw 'Wrong removal'
    }
    $script:removed = $true
}
function Remove-AppxProvisionedPackage {
    param($PackageName, [switch]$Online, $ErrorAction)
    if (-not $Online -or $PackageName -ne 'Microsoft.BingNews_1_x64__publisher') {
        throw 'Wrong provisioning'
    }
    $script:provisionRemoved = $true
    [PSCustomObject]@{RestartNeeded=$script:restart}
}
"""


@unittest.skipUnless(sys.platform == "win32", "Requires built-in Windows PowerShell")
class PowerShellIntegrationTests(unittest.TestCase):
    def test_shared_frameworks_are_protected_without_blocking_apps_with_resource_packs(self):
        from xnebula.core import available_apps
        from xnebula.windows import parse_inventory

        extra = r"""
$script:originalAppx = (Get-Item Function:\Get-AppxPackage).ScriptBlock
function Get-AppxPackage {
    param([switch]$AllUsers, $PackageTypeFilter, $ErrorAction)
    if ($PackageTypeFilter -notcontains 'Framework') { throw 'Framework inventory was omitted' }
    & $script:originalAppx -AllUsers -PackageTypeFilter $PackageTypeFilter
    [PSCustomObject]@{Name='Microsoft.OtherSharedFramework'; PackageFullName='framework';
        Publisher='CN=Microsoft Corporation'; PublisherId='publisher';
        IsFramework=$true; IsResourcePackage=$false; NonRemovable=$false}
    [PSCustomObject]@{Name='Microsoft.BingNews'; PackageFullName='resource';
        Publisher='CN=Microsoft Corporation'; PublisherId='publisher';
        IsFramework=$false; IsResourcePackage=$true; NonRemovable=$true}
}
function Get-AppxProvisionedPackage {
    param([switch]$Online, $ErrorAction)
    [PSCustomObject]@{DisplayName='Microsoft.OtherSharedFramework'; PackageName='shared_publisher'}
}
"""
        apps = available_apps(parse_inventory(bridge()._run(STUBS + extra + INVENTORY)))
        self.assertEqual([app.id for app in apps], ["news"])

    def test_force_close_only_targets_processes_inside_the_selected_app(self):
        stubs = STUBS.replace(
            "IsBundle=$true;", "IsBundle=$true; InstallLocation='C:\\XNebulaTest\\App';"
        )
        extra = r"""
$script:closed = @()
function Get-Process {
    param($ErrorAction)
    [PSCustomObject]@{Id=101; Path='C:\XNebulaTest\App\app.exe'}
    [PSCustomObject]@{Id=202; Path='C:\XNebulaTest\App-Other\app.exe'}
    [PSCustomObject]@{Id=303; Path=$null}
}
function Stop-Process {
    param($Id, [switch]$Force, $ErrorAction)
    if ($Id -ne 101 -or -not $Force) { throw 'Unrelated process was targeted' }
    $script:closed += $Id
}
function Remove-AppxPackage {
    param($Package, [switch]$AllUsers, $Confirm, $ErrorAction)
    if ($script:closed.Count -ne 1 -or -not $AllUsers) { throw 'Expected selected app to close' }
    $script:removed = $true
}
"""
        self.assertEqual(bridge()._run(stubs + extra + removal_script(NEWS)), "ok")

    def test_non_microsoft_publishers_are_not_offered_for_removal(self):
        from xnebula.core import available_apps
        from xnebula.windows import parse_inventory

        stubs = STUBS.replace("CN=Microsoft Corporation", "CN=Another Vendor")
        self.assertEqual(available_apps(parse_inventory(bridge()._run(stubs + INVENTORY))), [])

    def test_inventory_prefers_bundle_and_includes_provisioning(self):
        from xnebula.windows import parse_inventory

        rows = parse_inventory(bridge()._run(STUBS + INVENTORY))
        self.assertEqual([row.kind for row in rows], ["installed", "provisioned"])
        self.assertEqual(rows[0].full_name, NEWS.full_name)

    def test_inventory_keeps_main_package_for_a_different_version(self):
        from xnebula.windows import parse_inventory

        stubs = STUBS.replace("Version='1.0'; IsBundle=$false", "Version='2.0'; IsBundle=$false")
        rows = parse_inventory(bridge()._run(stubs + INVENTORY))
        self.assertIn("child", [row.full_name for row in rows])

    def test_removal_executes_and_verifies_both_scopes(self):
        for kind in ("installed", "provisioned"):
            with self.subTest(kind=kind):
                script = removal_script(Package(NEWS.name, NEWS.full_name, kind))
                self.assertEqual(bridge()._run(STUBS + script), "ok")

    def test_changed_protected_remaining_and_restart_results_fail(self):
        cases = (
            ("installed", "$script:removed=$true;"),
            ("installed", "$script:protected=$true;"),
            ("installed", "$script:keep=$true;"),
            ("provisioned", "$script:provisionRemoved=$true;"),
            ("provisioned", "$script:keep=$true;"),
            ("provisioned", "$script:restart=$true;"),
        )
        for kind, setup in cases:
            with self.subTest(kind=kind, setup=setup), self.assertRaises(BackendError):
                bridge()._run(
                    STUBS + setup + removal_script(Package(NEWS.name, NEWS.full_name, kind))
                )
