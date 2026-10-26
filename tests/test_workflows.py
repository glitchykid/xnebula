import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_app import FakeBackend
from test_settings import MemoryRegistry

from xnebula.cli import main
from xnebula.profiles import profile_commands, validate_profile
from xnebula.settings import BACKGROUND, SETTINGS, RegistryValue, plan_background, plan_settings


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        self.registry.background_apps = lambda: ["Example_publisher"]
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
        return main(args, backend=FakeBackend(), registry=self.registry)

    def test_lists_and_previews_do_not_write(self):
        for group in ("privacy", "storage", "recall", "startup", "background"):
            self.assertEqual(self.run_cli([group, "list"]), 0)
        for args in (
            ["privacy", "set", "all"],
            ["storage", "configure"],
            ["recall", "disable"],
            ["background", "disable", "Example_publisher"],
        ):
            self.assertEqual(self.run_cli(args), 0)
        self.assertEqual(self.registry.writes, [])

    def test_settings_apply_and_restore_round_trip_through_cli(self):
        args = ["privacy", "set", "location", "--apply", "--yes", "--log-dir", str(self.directory)]
        self.assertEqual(self.run_cli(args), 0)
        backup = next(self.directory.glob("settings-*.json"))
        self.assertEqual(
            self.run_cli(
                ["restore", str(backup), "--apply", "--yes", "--log-dir", str(self.directory)]
            ),
            0,
        )
        self.assertIsNone(self.registry.read(SETTINGS["location"].target))
        self.assertEqual(self.run_cli(["report", "--log-dir", str(self.directory)]), 0)
        self.assertIn("Verified: 1", self.output.getvalue())

    def test_confirmation_cancel_eof_and_interrupt_do_not_write(self):
        for answer in ("no", EOFError(), KeyboardInterrupt()):
            kwargs = (
                {"side_effect": answer}
                if isinstance(answer, BaseException)
                else {"return_value": answer}
            )
            with patch("builtins.input", **kwargs):
                self.assertIn(self.run_cli(["privacy", "set", "location", "--apply"]), (0, 130))
        self.assertEqual(self.registry.writes, [])

    def test_unsupported_edition_and_noop_are_visible(self):
        self.registry.edition = "Core"
        self.assertEqual(self.run_cli(["privacy", "set", "location"]), 0)
        self.assertIn("Unsupported", self.output.getvalue())
        self.assertIn("Nothing to change", self.output.getvalue())

    def test_startup_command_disables_only_selected_entry(self):
        target = self.registry.startup()["user:Example"]
        self.registry.values[target] = RegistryValue(1, "example.exe")
        self.assertEqual(
            self.run_cli(
                [
                    "startup",
                    "disable",
                    "user:Example",
                    "--apply",
                    "--yes",
                    "--log-dir",
                    str(self.directory),
                ]
            ),
            0,
        )
        self.assertIsNone(self.registry.read(target))

    def test_storage_retention_limits_and_preservation(self):
        for days in (-1, 366, True):
            with self.subTest(days=days), self.assertRaises(ValueError):
                plan_settings("storage", ["all"], self.registry, downloads_days=days)
        plan, _ = plan_settings("storage", ["all"], self.registry)
        self.assertEqual(plan[0].after.data, 0)
        self.assertEqual(plan[1].after.data, 0)
        self.assertEqual(plan[-1].label, "storage-enable")
        self.registry.values[SETTINGS["location"].target] = RegistryValue(1, "wrong")
        with self.assertRaises(ValueError):
            plan_settings("privacy", ["location"], self.registry)

    def test_background_merges_deny_list_and_removes_conflicting_exceptions(self):
        self.registry.values[BACKGROUND["deny"]] = RegistryValue(7, ["Other_publisher"])
        self.registry.values[BACKGROUND["allow"]] = RegistryValue(
            7, ["Example_publisher", "Allowed_publisher"]
        )
        plan = plan_background(["Example_publisher"], self.registry)
        values = {change.label: change.after.data for change in plan}
        self.assertEqual(values["background-deny"], ["Example_publisher", "Other_publisher"])
        self.assertEqual(values["background-allow"], ["Allowed_publisher"])
        for families in ([], ["unknown"], ["*"]):
            with self.assertRaises(ValueError):
                plan_background(families, self.registry)
        self.registry.values[BACKGROUND["deny"]] = RegistryValue(1, "wrong")
        with self.assertRaises(ValueError):
            plan_background(["Example_publisher"], self.registry)
        self.registry.edition = "Core"
        with self.assertRaises(ValueError):
            plan_background(["Example_publisher"], self.registry)

    def test_profile_save_preview_apply_and_no_overwrite(self):
        path = self.directory / "profile.json"
        self.assertEqual(
            self.run_cli(
                [
                    "profile",
                    "save",
                    str(path),
                    "--privacy",
                    "location",
                    "--apps",
                    "news",
                    "--storage",
                    "--recall",
                    "--background",
                    "Example_publisher",
                ]
            ),
            0,
        )
        self.assertEqual(self.run_cli(["profile", "save", str(path)]), 1)
        self.assertEqual(self.run_cli(["profile", "run", str(path)]), 0)
        self.assertEqual(self.registry.writes, [])
        with patch("builtins.input", return_value="no"):
            self.assertEqual(self.run_cli(["profile", "run", str(path), "--apply"]), 0)
        self.assertEqual(self.registry.writes, [])
        self.assertEqual(
            self.run_cli(
                ["profile", "run", str(path), "--apply", "--yes", "--log-dir", str(self.directory)]
            ),
            0,
        )
        self.assertTrue(self.registry.writes)

    def test_profile_validation_and_preflight_stop_before_mutation(self):
        path = self.directory / "profile.json"
        self.run_cli(
            ["profile", "save", str(path), "--privacy", "location", "--startup", "unknown"]
        )
        self.assertEqual(self.run_cli(["profile", "run", str(path), "--apply", "--yes"]), 1)
        self.assertEqual(self.registry.writes, [])
        good = json.loads(path.read_text())
        for field, value in (
            ("schema", 2),
            ("privacy", ["unknown"]),
            ("apps", ["--apply"]),
            ("storage", 1),
            ("downloads_days", -1),
            ("startup", "name"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_profile({**good, field: value})
        self.assertTrue(profile_commands(good))

    def test_report_handles_empty_and_truncated_journals(self):
        self.assertEqual(self.run_cli(["report", "--log-dir", str(self.directory)]), 0)
        (self.directory / "broken.jsonl").write_text('{"status":"started"}\n{"broken"\nnull\n')
        self.assertEqual(self.run_cli(["report", "--log-dir", str(self.directory)]), 0)
        self.assertIn("unfinished: 1", self.output.getvalue())
        self.assertIn("Unreadable", self.output.getvalue())
