import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_system_actions
from test_app import FakeBackend
from test_settings import MemoryRegistry
from test_system_actions import MemoryServices

from xnebula.cli import main
from xnebula.edge import EdgeInstallation
from xnebula.services import ServiceState
from xnebula.settings import PERMISSION_EXCEPTIONS, SETTINGS, RegistryValue, plan_settings


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        self.services = MemoryServices([ServiceState("DiagTrack", "Auto", "Running")])
        self.animations = test_system_actions.AnimationTests().manager()
        self.edge = Mock()
        self.edge.remove.return_value = "uninstalled"
        self.edge.inventory.return_value = [EdgeInstallation("edge.exe", "setup.exe", True)]
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)
        self.errors = contextlib.redirect_stderr(self.output)
        self.errors.__enter__()
        self.addCleanup(self.errors.__exit__, None, None, None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def run_cli(self, args):
        return main(
            args,
            backend=FakeBackend(),
            registry=self.registry,
            services=self.services,
            animations=self.animations,
            edge=self.edge,
        )

    def flags(self):
        return ["--apply", "--yes", "--log-dir", str(self.directory)]

    def test_all_preview_commands_make_no_changes(self):
        for args in (
            ["privacy", "list"],
            ["privacy", "set", "all"],
            ["services", "list"],
            ["services", "disable", "all"],
            ["animations", "disable"],
            ["edge", "remove"],
        ):
            self.assertEqual(self.run_cli(args), 0)
        self.assertEqual(self.registry.writes, [])
        self.assertEqual(self.services.calls, [])
        self.animations.configure.assert_not_called()
        self.edge.remove.assert_not_called()

    def test_privacy_apply_and_restore_preserve_existing_values(self):
        self.assertEqual(self.run_cli(["privacy", "set", "location", *self.flags()]), 0)
        backup = next(self.directory.glob("settings-*.json"))
        self.assertEqual(self.run_cli(["restore", str(backup), *self.flags()]), 0)
        self.assertIsNone(self.registry.read(SETTINGS["location"].target))

    def test_service_and_animation_backups_are_routed_to_correct_restore_handler(self):
        for command, kind in (
            (["services", "disable", "all"], "services"),
            (["animations", "disable"], "animations"),
        ):
            self.assertEqual(self.run_cli([*command, *self.flags()]), 0)
            path = next(self.directory.glob(kind + "-*.json"))
            self.assertEqual(self.run_cli(["restore", str(path)]), 0)
            self.assertEqual(self.run_cli(["restore", str(path), *self.flags()]), 0)

    def test_force_edge_uninstall_requires_apply_and_can_report_absence(self):
        self.assertEqual(self.run_cli(["edge", "remove", *self.flags()]), 0)
        self.edge.remove.assert_called_once()
        self.edge.inventory.return_value = []
        self.assertEqual(self.run_cli(["edge", "remove"]), 0)
        self.assertIn("not installed", self.output.getvalue())

    def test_confirm_cancel_eof_and_interrupt_make_no_changes(self):
        for answer in ("no", EOFError(), KeyboardInterrupt()):
            kwargs = (
                {"side_effect": answer}
                if isinstance(answer, BaseException)
                else {"return_value": answer}
            )
            with patch("builtins.input", **kwargs):
                self.assertIn(self.run_cli(["privacy", "set", "location", "--apply"]), (0, 130))
        self.assertEqual(self.registry.writes, [])

    def test_home_edition_skips_unsupported_policy_settings(self):
        self.registry.edition = "Core"
        self.assertEqual(self.run_cli(["privacy", "set", "all"]), 0)
        self.assertIn("unsupported edition", self.output.getvalue())

    def test_privacy_clears_exceptions_that_would_override_a_force_deny(self):
        target = next(
            target
            for target in PERMISSION_EXCEPTIONS
            if target.name == "LetAppsAccessCamera_ForceAllowTheseApps"
        )
        self.registry.values[target] = RegistryValue(7, ["Allowed_publisher"])
        plan, _ = plan_settings("privacy", ["camera"], self.registry)
        self.assertTrue(
            any(change.target == target and change.after == RegistryValue(7, []) for change in plan)
        )
        self.assertEqual(self.run_cli(["privacy", "set", "camera", *self.flags()]), 0)
        self.assertEqual(self.registry.read(target), RegistryValue(7, []))

    def test_unexpected_policy_type_and_malformed_backups_fail(self):
        self.registry.values[SETTINGS["location"].target] = RegistryValue(1, "wrong")
        self.assertEqual(self.run_cli(["privacy", "set", "location"]), 1)
        for data in ("null", '{"kind":"unknown"}', "not-json"):
            path = self.directory / "invalid.json"
            path.write_text(data)
            self.assertEqual(self.run_cli(["restore", str(path)]), 1)

    def test_removed_features_are_no_longer_commands(self):
        for command in ("profile", "startup", "storage", "background", "report", "recall"):
            with self.subTest(command=command), self.assertRaises(SystemExit) as error:
                self.run_cli([command])
            self.assertEqual(error.exception.code, 2)

    def test_menu_does_not_request_apply_for_an_empty_preview(self):
        self.edge.inventory.return_value = []
        self.services.states.clear()
        for answers in (["5", "0"], ["2", "all", "0"]):
            with patch("builtins.input", side_effect=answers):
                self.assertEqual(self.run_cli(["menu"]), 0)
        self.edge.remove.assert_not_called()
