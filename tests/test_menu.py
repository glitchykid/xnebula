import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from xnebula.cli import main
from xnebula.core import CATALOG, Package
from xnebula.menu import choose_items, parse_app_selection, run_menu


class MenuTests(unittest.TestCase):
    def test_terminal_picker_uses_checkboxes_without_descriptions(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.menu.sys.stdin.isatty", return_value=True),
            patch("xnebula.menu.sys.stdout.isatty", return_value=True),
            patch("xnebula.menu.enable_virtual_terminal", return_value=True),
            patch("xnebula.menu.select_items", return_value=[1]) as select,
        ):
            command = choose_items(
                [("one", "First", "Long description"), ("two", "Second", "Other effect")],
                ["remove"],
                "Apps",
            )
        select.assert_called_once_with(["First", "Second"])
        self.assertEqual(command, ["remove", "two"])
        self.assertNotIn("Long description", output.getvalue())

    def test_terminal_without_virtual_terminal_uses_numbered_fallback(self):
        for answer, expected in (("1", ["remove", "one"]), ("all", ["remove", "one"]), ("", None)):
            with (
                self.subTest(answer=answer),
                contextlib.redirect_stdout(io.StringIO()) as output,
                patch("xnebula.menu.sys.stdin.isatty", return_value=True),
                patch("xnebula.menu.sys.stdout.isatty", return_value=True),
                patch("xnebula.menu.enable_virtual_terminal", return_value=False),
                patch("xnebula.menu.select_items") as select,
                patch("builtins.input", return_value=answer),
            ):
                command = choose_items([("one", "First", "Effect")], ["remove"], "Apps")
                select.assert_not_called()
                self.assertEqual(command, expected)
                self.assertIn("Select All (1 items)", output.getvalue())

    def test_dumb_terminal_can_select_apps_without_escape_sequences(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.menu.sys.stdin.isatty", return_value=True),
            patch("xnebula.menu.sys.stdout.isatty", return_value=True),
            patch.dict("os.environ", {"TERM": "dumb"}),
            patch("builtins.input", return_value="1"),
        ):
            command = choose_items([("one", "First", "Effect")], ["remove"], "Apps")
        self.assertEqual(command, ["remove", "one"])
        self.assertNotIn("\x1b", output.getvalue())

    def test_launcher_does_not_override_console_theme(self):
        script = (Path(__file__).resolve().parents[1] / "scripts/launch.ps1").read_text()
        self.assertNotIn("BackgroundColor", script)
        self.assertNotIn("ForegroundColor", script)
        self.assertNotIn("[Console]::Clear", script)

    def run_menu(self, answers, invoke=None, **kwargs):
        invoke = invoke or Mock(return_value=0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("builtins.input", side_effect=answers):
            code = run_menu(invoke, **kwargs)
        return code, output.getvalue(), invoke

    def test_menu_contains_only_windows_actions_and_recovery(self):
        _, output, invoke = self.run_menu(["invalid", "0"])
        for name in (
            "Remove Windows apps",
            "optional services",
            "privacy",
            "animations",
            "Edge",
            "backup",
        ):
            self.assertIn(name, output)
        for removed in ("Startup entries", "Storage cleanup", "saved profile", "Change reports"):
            self.assertNotIn(removed, output)
        invoke.assert_not_called()

    def test_removal_numbers_select_all_and_cancellation(self):
        _, output, invoke = self.run_menu(["1", "999", "1,3-4", "", "0"])
        self.assertIn("Invalid selection", output)
        self.assertIn("Select All", output)
        invoke.assert_called_once_with(["remove", "news", "solitaire", "clipchamp"])
        _, _, invoke = self.run_menu(["1", "all", "APPLY", "0"])
        command = ["remove", *(app.id for app in CATALOG)]
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            [command, [*command, "--apply", "--yes"]],
        )
        for value in ("", "0"):
            self.run_menu(["1", value, "0"])[2].assert_not_called()

    def test_service_selection_is_numbered_and_privacy_is_one_step(self):
        _, _, invoke = self.run_menu(["2", "1", "", "3", "APPLY", "4", "", "5", "", "0"])
        calls = [call.args[0] for call in invoke.call_args_list]
        self.assertIn(["services", "disable", "DiagTrack"], calls)
        self.assertIn(["privacy", "set", "all", "--apply", "--yes"], calls)
        self.assertIn(["animations", "disable"], calls)
        self.assertIn(["edge", "remove"], calls)

    def test_failed_preview_does_not_offer_apply(self):
        invoke = Mock(return_value=1)
        self.run_menu(["5", "0"], invoke)
        invoke.assert_called_once_with(["edge", "remove"])

    def test_confirmation_typo_keeps_preview_and_requires_exact_apply(self):
        _, output, invoke = self.run_menu(["3", "apply", "APPL", " APPLY ", "0"])
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            [["privacy", "set", "all"], ["privacy", "set", "all", "--apply", "--yes"]],
        )
        self.assertEqual(output.count("Type APPLY exactly, or press Enter to cancel."), 2)

    def test_confirmation_typo_can_be_cancelled_without_applying(self):
        _, output, invoke = self.run_menu(["5", "yes", " ", "0"])
        invoke.assert_called_once_with(["edge", "remove"])
        self.assertIn("Type APPLY exactly, or press Enter to cancel.", output)

    def test_interrupted_confirmation_never_applies(self):
        for error in (EOFError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                code, _, invoke = self.run_menu(["3", error])
                self.assertEqual(code, 130)
                invoke.assert_called_once_with(["privacy", "set", "all"])

    def test_failed_or_empty_inventory_returns_to_menu(self):
        self.run_menu(["1", "0"], apps_provider=lambda: [])[2].assert_not_called()
        provider = Mock(side_effect=OSError("administrator required"))
        _, output, _ = self.run_menu(["1", "0"], apps_provider=provider)
        self.assertIn("administrator required", output)

    def test_backups_can_be_restored_by_number_without_typing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "backup with spaces.json"
            path.write_text(json.dumps({"schema": 1, "changes": []}))
            (root / "invalid.json").write_text("invalid")
            (root / "foreign.json").write_text('{"schema":2}')
            _, _, invoke = self.run_menu(["6", "999", "1", "", "0"], backups_dir=root)
            invoke.assert_called_once_with(["restore", str(path)])
        _, output, _ = self.run_menu(["6", "0"], backups_dir=Path("no-such-backup-folder"))
        self.assertIn("No settings backups", output)

    def test_eof_and_interrupt_exit_cleanly(self):
        for error in (EOFError(), KeyboardInterrupt()):
            self.assertEqual(self.run_menu([error])[0], 130)

    def test_interactive_no_arguments_opens_menu_and_pipes_display_help(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("xnebula.cli.run_menu", return_value=0) as menu,
        ):
            self.assertEqual(main([]), 0)
            menu.assert_called_once()
        with (
            patch("sys.stdin.isatty", return_value=False),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main([]), 0)
        self.assertIn("usage:", output.getvalue())


class AppSelectionTests(unittest.TestCase):
    def test_number_formats_and_duplicate_entries_follow_display_order(self):
        self.assertEqual(parse_app_selection("4, 1 2-3,2"), [app.id for app in CATALOG[:4]])
        for value in (str(len(CATALOG) + 1), "A", "all", "Select All"):
            self.assertEqual(parse_app_selection(value), [app.id for app in CATALOG])
        for value in ("", " ", "0"):
            self.assertEqual(parse_app_selection(value), [])

    def test_invalid_input_never_partially_selects_apps(self):
        for value in (
            "1 bad",
            "-1",
            "0 1",
            "1,9",
            "all 1",
            "9-9",
            "3-1",
            "1-99",
            "1-",
            "1-2-3",
            ",",
            "--apply",
            "1.0",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_app_selection(value)

    def test_detected_list_drives_preview_and_apply(self):
        from test_app import FakeBackend

        packages = [
            Package("Microsoft.Windows.Photos", "photos_1", "installed"),
            Package("Microsoft.WindowsStore", "store_1", "provisioned"),
        ]
        for confirmation in ("", "APPLY"):
            backend = FakeBackend(packages)
            with (
                tempfile.TemporaryDirectory() as directory,
                contextlib.chdir(directory),
                contextlib.redirect_stdout(io.StringIO()) as output,
                patch("builtins.input", side_effect=["1", "all", confirmation, "0"]),
            ):
                self.assertEqual(main(["menu"], backend=backend), 0)
            self.assertIn("Photos", output.getvalue())
            self.assertEqual(backend.removed, packages if confirmation else [])
