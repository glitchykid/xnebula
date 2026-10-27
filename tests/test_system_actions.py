import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from xnebula.animations import (
    ANIMATION_FLAGS,
    AnimationState,
    disable_animations,
    restore_animations,
)
from xnebula.edge import EdgeInstallation, WindowsEdge
from xnebula.services import (
    ServiceChange,
    ServiceState,
    apply_service_changes,
    plan_services,
    restore_services,
)
from xnebula.windows import BackendError


class MemoryServices:
    identity = {"machine": "test", "user": "S-1-test"}

    def __init__(self, states):
        self.states = {state.name: state for state in states}
        self.calls = []

    def inventory(self, names=None):
        return [state for state in self.states.values() if names is None or state.name in names]

    def configure(self, change):
        self.calls.append(change)
        self.states[change.after.name] = change.after


class ServiceTests(unittest.TestCase):
    def test_disable_all_skips_absent_services_and_protects_external_dependents(self):
        states = [
            ServiceState("DiagTrack", "Auto", "Running"),
            ServiceState("Spooler", "Auto", "Running", dependents=("ImportantService",)),
        ]
        changes, skipped = plan_services(["all"], states)
        self.assertEqual([change.before.name for change in changes], ["DiagTrack"])
        self.assertTrue(any("Spooler" in reason for reason in skipped))

    def test_unknown_and_essential_services_cannot_be_disabled(self):
        for ids in ([], ["WinDefend"], ["RpcSs"], ["*"], ["all", "DiagTrack"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                plan_services(ids, [])

    def test_dependent_optional_services_are_stopped_before_their_parent(self):
        states = [
            ServiceState("XblAuthManager", "Manual", "Running", dependents=("XblGameSave",)),
            ServiceState("XblGameSave", "Manual", "Running"),
        ]
        changes, skipped = plan_services(["all"], states)
        self.assertFalse(skipped)
        self.assertEqual(
            [change.before.name for change in changes], ["XblGameSave", "XblAuthManager"]
        )

    def test_apply_and_restore_preserve_startup_delayed_auto_and_running_state(self):
        original = ServiceState("DiagTrack", "Auto", "Running", delayed=True)
        manager = MemoryServices([original])
        changes, _ = plan_services(["DiagTrack"], manager.inventory())
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            backup = apply_service_changes(changes, manager, Path(directory))
            self.assertEqual(manager.states[original.name].start_mode, "Disabled")
            restore_services(backup, manager, Path(directory))
            self.assertEqual(manager.states[original.name], original)
            count = len(manager.calls)
            restore_services(backup, manager, Path(directory))
            self.assertEqual(len(manager.calls), count)

    def test_stale_plan_backup_failure_and_foreign_backup_make_no_changes(self):
        manager = MemoryServices([ServiceState("DiagTrack", "Auto", "Running")])
        changes, _ = plan_services(["all"], manager.inventory())
        manager.states["DiagTrack"] = ServiceState("DiagTrack", "Manual", "Stopped")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            apply_service_changes(changes, manager, Path(directory))
        self.assertEqual(manager.calls, [])

    def test_service_backups_cannot_target_arbitrary_services(self):
        state = ServiceState("WinDefend", "Auto", "Running")
        manager = MemoryServices([state])
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            apply_service_changes(
                [ServiceChange(state, ServiceState("WinDefend", "Disabled", "Stopped"))],
                manager,
                Path(directory),
            )
        self.assertEqual(manager.calls, [])


class AnimationTests(unittest.TestCase):
    def manager(self):
        manager = Mock()
        manager.identity = {"machine": "test", "user": "user"}
        manager.state = AnimationState({flag.id: True for flag in ANIMATION_FLAGS}, None)
        manager.read.side_effect = lambda: manager.state
        manager.configure.side_effect = lambda before, after: setattr(manager, "state", after)
        return manager

    def test_disable_and_restore_every_supported_windows_animation(self):
        manager = self.manager()
        original = manager.state
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            backup = disable_animations(manager, Path(directory))
            self.assertTrue(all(value is False for value in manager.state.values.values()))
            restore_animations(backup, manager, Path(directory))
            self.assertEqual(manager.state, original)

    def test_backup_exists_before_any_animation_is_changed(self):
        manager = self.manager()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):

            def configure(before, after):
                self.assertTrue(list(Path(directory).glob("animations-*.json")))
                raise OSError("Windows rejected the setting")

            manager.configure.side_effect = configure
            with self.assertRaises(OSError):
                disable_animations(manager, Path(directory))
            self.assertEqual(manager.state.values[ANIMATION_FLAGS[0].id], True)

    def test_foreign_or_invalid_animation_backup_is_rejected(self):
        manager = self.manager()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            path = disable_animations(manager, Path(directory))
            document = json.loads(path.read_text())
            document["identity"]["machine"] = "other"
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                restore_animations(path, manager, Path(directory))


class EdgeTests(unittest.TestCase):
    def test_force_uninstall_targets_edge_and_preserves_webview(self):
        bridge = Mock()
        bridge._run.return_value = "uninstalled"
        manager = WindowsEdge(bridge=bridge)
        manager.remove(
            EdgeInstallation(
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\130.0.1.2\Installer\setup.exe",
                True,
            )
        )
        script = bridge._run.call_args.args[0]
        self.assertIn("--force-uninstall", script)
        self.assertIn("Get-AuthenticodeSignature", script)
        self.assertNotIn("--delete-profile", script)
        self.assertIn("Remove-Item -LiteralPath $root", script)
        self.assertIn("ReparsePoint", script)
        self.assertIn("Stop-Process", script)

    def test_edge_removal_is_not_reported_successful_without_confirmation(self):
        bridge = Mock()
        bridge._run.return_value = "still installed"
        with self.assertRaises(BackendError):
            WindowsEdge(bridge=bridge).remove(EdgeInstallation("edge.exe", "setup.exe", True))

    def test_edge_inventory_rejects_invalid_data(self):
        bridge = Mock()
        manager = WindowsEdge(bridge=bridge)
        for value in ("null", "{}", "[1]", "[{}]", ""):
            bridge._run.return_value = value
            with self.subTest(value=value), self.assertRaises(BackendError):
                manager.inventory()
