"""Test native adapters with substitute APIs/cmdlets; never mutate the host PC."""

import ctypes
import json
import sys
import unittest
from unittest.mock import Mock

from test_settings import MemoryRegistry
from test_windows import bridge

from xnebula.animations import ANIMATION_FLAGS, AnimationInfo, WindowsAnimations
from xnebula.edge import EdgeInstallation, WindowsEdge
from xnebula.services import ServiceChange, ServiceState, WindowsServices
from xnebula.settings import ANIMATION_TASKBAR, RegistryValue
from xnebula.windows import BackendError


class FakeUser32:
    def __init__(self):
        self.values = {flag.id: True for flag in ANIMATION_FLAGS}
        self.fail = None

    def SystemParametersInfoW(self, action, size, pointer, flags):
        if action == self.fail:
            return 0
        for option in ANIMATION_FLAGS:
            if action == option.get_action:
                if option.id == "minimize-restore":
                    assert size == ctypes.sizeof(AnimationInfo)
                    pointer._obj.iMinAnimate = int(self.values[option.id])
                else:
                    pointer._obj.value = int(self.values[option.id])
                return 1
            if action == option.set_action:
                assert flags == 3
                if option.id == "minimize-restore":
                    self.values[option.id] = bool(pointer._obj.iMinAnimate)
                else:
                    self.values[option.id] = bool(pointer.value)
                return 1
        raise AssertionError("Unexpected Windows preference API")


class AnimationAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        self.api = FakeUser32()
        self.manager = WindowsAnimations(registry=self.registry, user32=self.api)

    def test_all_windows_preferences_and_taskbar_round_trip(self):
        from xnebula.animations import AnimationState

        original = self.manager.read()
        disabled = AnimationState({flag.id: False for flag in ANIMATION_FLAGS}, RegistryValue(4, 0))
        self.manager.configure(original, disabled)
        self.assertEqual(self.manager.read(), disabled)
        self.manager.configure(disabled, original)
        self.assertEqual(self.manager.read(), original)

    def test_native_read_and_write_errors_are_reported(self):
        from xnebula.animations import AnimationState

        before = self.manager.read()
        for action in (ANIMATION_FLAGS[0].get_action, ANIMATION_FLAGS[0].set_action):
            self.api.fail = action
            with self.subTest(action=action), self.assertRaises(OSError):
                self.manager.configure(
                    before, AnimationState({flag.id: False for flag in ANIMATION_FLAGS}, None)
                )
        self.api.fail = None
        self.registry.values[ANIMATION_TASKBAR] = RegistryValue(1, "invalid")
        with self.assertRaises(ValueError):
            self.manager.read()


class PrefixBridge:
    def __init__(self, prefix):
        self.prefix = prefix

    def _run(self, script):
        return bridge()._run(self.prefix + script)


SERVICE_STUBS = r"""
$script:mode = 'Auto'; $script:status = 'Running'; $script:delayed = $true
$script:dependent = $false; $script:scFail = $false
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($ClassName -ne 'Win32_Service') { throw 'Wrong CIM class' }
    if ($Filter -ne "Name='DiagTrack'") { return }
    [PSCustomObject]@{Name='DiagTrack'; StartMode=$script:mode; DelayedAutoStart=$script:delayed}
}
function Get-Service {
    param($Name, $ErrorAction)
    if ($Name -ne 'DiagTrack') { throw 'Wrong service' }
    $dependencies = @()
    if ($script:dependent) {
        $dependencies = @([PSCustomObject]@{Name='RpcSs'; Status='Running'})
    }
    $s = [PSCustomObject]@{Name=$Name; Status=$script:status; DependentServices=$dependencies}
    $s | Add-Member -MemberType ScriptMethod -Name WaitForStatus -Value {
        param($wanted, $timeout)
        if ($script:status -ne [string]$wanted) { throw 'Service did not reach requested state' }
    }
    $s
}
function Invoke-XNebulaFakeSc {
    param($Command, $Name, $Start, $Mode)
    if ($Command -ne 'config' -or $Name -ne 'DiagTrack' -or $Start -ne 'start=') {
        throw 'Unexpected service configuration'
    }
    $global:LASTEXITCODE = 0
    if ($script:scFail) { $global:LASTEXITCODE = 5; return }
    if ($Mode -eq 'disabled') { $script:mode = 'Disabled' }
    elseif ($Mode -eq 'demand') { $script:mode = 'Manual' }
    elseif ($Mode -eq 'auto') { $script:mode = 'Auto'; $script:delayed = $false }
    elseif ($Mode -eq 'delayed-auto') { $script:mode = 'Auto'; $script:delayed = $true }
    else { throw 'Wrong startup mode' }
}
$scPath = $env:SystemRoot + '\System32\sc.exe'
Set-Alias -Name $scPath -Value Invoke-XNebulaFakeSc -ErrorAction Stop
if ((Get-Alias -Name $scPath).Definition -ne 'Invoke-XNebulaFakeSc') {
    throw 'Native service mutation was not intercepted'
}
function Stop-Service {
    param($Name, $ErrorAction)
    if ($Name -ne 'DiagTrack') { throw 'Wrong stop target' }
    $script:status = 'Stopped'
}
function Start-Service {
    param($Name, $ErrorAction)
    if ($Name -ne 'DiagTrack') { throw 'Wrong start target' }
    $script:status = 'Running'
}
"""


@unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell")
class ServiceAdapterTests(unittest.TestCase):
    def manager(self, extra=""):
        return WindowsServices(
            bridge=PrefixBridge(SERVICE_STUBS + extra), identity={"machine": "test", "user": "user"}
        )

    def test_inventory_reads_optional_services_and_delayed_start(self):
        self.assertEqual(
            self.manager().inventory(), [ServiceState("DiagTrack", "Auto", "Running", True)]
        )

    def test_disable_and_restore_commands_use_native_service_controls(self):
        before = ServiceState("DiagTrack", "Auto", "Running", True)
        after = ServiceState("DiagTrack", "Disabled", "Stopped")
        self.manager().configure(ServiceChange(before, after))
        self.manager("$script:mode='Disabled'; $script:status='Stopped';").configure(
            ServiceChange(after, before)
        )
        manual = ServiceState("DiagTrack", "Manual", "Stopped")
        self.manager().configure(ServiceChange(before, manual))
        disabled_running = ServiceState("DiagTrack", "Disabled", "Running")
        self.manager("$script:mode='Disabled'; $script:status='Stopped';").configure(
            ServiceChange(after, disabled_running)
        )

    def test_changed_service_dependencies_and_configuration_errors_are_not_forced(self):
        before = ServiceState("DiagTrack", "Auto", "Running", True)
        after = ServiceState("DiagTrack", "Disabled", "Stopped")
        for extra in (
            "$script:dependent=$true;",
            "$script:mode='Manual';",
            "$script:scFail=$true;",
        ):
            with self.subTest(extra=extra), self.assertRaises(BackendError):
                self.manager(extra).configure(ServiceChange(before, after))


EDGE_STUBS = r"""
$script:edgeRoot = Join-Path $env:ProgramFiles 'Microsoft\Edge\Application'
$script:fixtureExe = Join-Path $script:edgeRoot 'msedge.exe'
$script:fixtureSetup = Join-Path $script:edgeRoot '130.0.1.2\Installer\setup.exe'
$script:removed=$false; $script:keep=$false; $script:badSignature=$false
$script:purged=$false; $script:link=$false; $script:childLink=$false
$script:missingInstaller=$false
function Test-Path {
    param($LiteralPath, $PathType)
    if ($LiteralPath -eq $script:fixtureExe) {
        return (-not $script:purged -and (-not $script:removed -or $script:keep))
    }
    if ($LiteralPath -eq $script:edgeRoot) { return (-not $script:purged) }
    return $LiteralPath -eq $script:fixtureSetup
}
function Get-ChildItem {
    param($LiteralPath, [switch]$Directory, [switch]$Recurse, [switch]$Force, $ErrorAction)
    if ($LiteralPath -ne $script:edgeRoot) { throw 'Wrong Edge root' }
    if ($Directory) {
        if (-not $script:missingInstaller) {
            [PSCustomObject]@{Name='130.0.1.2'; FullName=(Join-Path $script:edgeRoot '130.0.1.2')}
        }
    } else {
        $attributes = [IO.FileAttributes]::Normal
        if ($script:childLink) { $attributes = [IO.FileAttributes]::ReparsePoint }
        [PSCustomObject]@{Name='msedge.exe'; Attributes=$attributes; PSIsContainer=$false}
    }
}
function Get-Item {
    param($LiteralPath, [switch]$Force, $ErrorAction)
    $attributes = [IO.FileAttributes]::Directory
    if ($script:link) { $attributes = $attributes -bor [IO.FileAttributes]::ReparsePoint }
    [PSCustomObject]@{Attributes=$attributes; PSIsContainer=$true}
}
function Invoke-XNebulaFakePermission {
    param([Parameter(ValueFromRemainingArguments=$true)]$Values)
    if ($Values -notcontains $script:edgeRoot) { throw 'Permission change escaped Edge root' }
    $global:LASTEXITCODE = 0
}
foreach ($nativeTool in @('takeown.exe', 'icacls.exe')) {
    $permissionPath = $env:SystemRoot + '\System32\' + $nativeTool
    Set-Alias -Name $permissionPath -Value Invoke-XNebulaFakePermission -ErrorAction Stop
    if ((Get-Alias -Name $permissionPath).Definition -ne 'Invoke-XNebulaFakePermission') {
        throw 'Native permission changes were not intercepted'
    }
}
function Remove-Item {
    param($LiteralPath, [switch]$Recurse, [switch]$Force, $ErrorAction)
    if ($LiteralPath -ne $script:edgeRoot -or -not $Recurse -or -not $Force) {
        throw 'Deletion escaped the validated Edge folder'
    }
    $script:purged = $true
}
function Get-AuthenticodeSignature {
    param($LiteralPath, $ErrorAction)
    $status = 'Valid'
    if ($script:badSignature) { $status = 'NotTrusted' }
    [PSCustomObject]@{Status=$status; SignerCertificate=[PSCustomObject]@{
        Subject='CN=Microsoft Corporation, O=Microsoft Corporation'}}
}
function Get-Process {
    param($Name, $ErrorAction)
    if ($Name -ne 'msedge') { throw 'Must not close unrelated or WebView processes' }
    [PSCustomObject]@{Id=777; Path=$script:fixtureExe}
}
function Stop-Process {
    param($Id, [switch]$Force, $ErrorAction)
    if ($Id -ne 777 -or -not $Force) { throw 'Wrong forced browser close' }
}
function Start-Process {
    param($FilePath, $ArgumentList, [switch]$Wait, [switch]$PassThru, $WindowStyle)
    if ($FilePath -ne $script:fixtureSetup -or $ArgumentList -notcontains '--force-uninstall' -or
        $ArgumentList -contains '--delete-profile' -or $WindowStyle -ne 'Hidden') {
        throw 'Unexpected browser uninstall arguments'
    }
    $script:removed = $true
    [PSCustomObject]@{ExitCode=0}
}
"""


@unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell")
class EdgeAdapterTests(unittest.TestCase):
    def test_inventory_and_force_uninstall_use_only_the_signed_vendor_installer(self):
        manager = WindowsEdge(bridge=PrefixBridge(EDGE_STUBS))
        inventory = manager.inventory()
        self.assertEqual(len(inventory), 1)
        self.assertTrue(inventory[0].system)
        self.assertEqual(manager.remove(inventory[0]), "uninstalled")

    def test_blocked_uninstall_force_deletes_only_edge_application_files(self):
        manager = WindowsEdge(bridge=PrefixBridge(EDGE_STUBS + "$script:keep=$true;"))
        self.assertEqual(manager.remove(manager.inventory()[0]), "force-deleted")

    def test_force_deletion_can_handle_a_missing_vendor_uninstaller(self):
        manager = WindowsEdge(bridge=PrefixBridge(EDGE_STUBS + "$script:missingInstaller=$true;"))
        item = manager.inventory()[0]
        self.assertEqual(item.installer, "")
        self.assertEqual(manager.remove(item), "force-deleted")

    def test_signature_failure_and_remaining_browser_are_errors(self):
        for setup in (
            "$script:badSignature=$true;",
            "$script:keep=$true; $script:link=$true;",
            "$script:keep=$true; $script:childLink=$true;",
        ):
            manager = WindowsEdge(bridge=PrefixBridge(EDGE_STUBS + setup))
            item = manager.inventory()[0]
            with self.subTest(setup=setup), self.assertRaises(BackendError):
                manager.remove(item)

    def test_paths_outside_the_known_edge_installation_are_rejected(self):
        from dataclasses import replace

        manager = WindowsEdge(bridge=PrefixBridge(EDGE_STUBS))
        item = manager.inventory()[0]
        for invalid in (
            replace(item, executable=r"C:\Windows\msedge.exe"),
            replace(item, installer=r"C:\Windows\Installer\setup.exe"),
        ):
            with self.subTest(item=invalid), self.assertRaises(BackendError):
                manager.remove(invalid)


class NativeInventoryValidationTests(unittest.TestCase):
    def test_services_reject_malformed_or_arbitrary_inventory(self):
        native = Mock()
        manager = WindowsServices(bridge=native, identity={})
        for value in (
            "null",
            "{}",
            "[1]",
            "[] trailing",
            '[{"name":"WinDefend","start_mode":"Auto","status":"Running","delayed":false,"dependents":[]}]',
        ):
            native._run.return_value = value
            with self.subTest(value=value), self.assertRaises(BackendError):
                manager.inventory()

    def test_edge_accepts_valid_inventory_and_rejects_missing_installer(self):
        native = Mock()
        native._run.return_value = json.dumps(
            [{"executable": "edge.exe", "installer": "", "system": True}]
        )
        manager = WindowsEdge(bridge=native)
        self.assertEqual(manager.inventory(), [EdgeInstallation("edge.exe", "", True)])
        with self.assertRaises(BackendError):
            manager.remove(manager.inventory()[0])
