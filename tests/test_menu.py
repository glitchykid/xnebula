import contextlib
import io
import tempfile
import unittest
from unittest.mock import Mock, patch

from xnebula.cli import main
from xnebula.core import CATALOG, Package
from xnebula.menu import parse_app_selection, run_menu


class MenuTests(unittest.TestCase):
    def run_menu(self, answers, invoke=None):
        invoke = invoke or Mock(return_value=0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("builtins.input", side_effect=answers):
            code = run_menu(invoke)
        return code, output.getvalue(), invoke

    def test_quit_and_invalid_selection_never_execute_a_command(self):
        code, output, invoke = self.run_menu(["invalid", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Choose a number", output)
        invoke.assert_not_called()

    def test_removal_previews_by_default_and_returns_to_menu(self):
        _, output, invoke = self.run_menu(["2", "1,2", "", "0"])
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            [
                ["remove", "news", "weather"],
            ],
        )
        self.assertIn("1  Microsoft News", output)
        self.assertIn("Select All", output)
        self.assertIn("Selected 2 apps: Microsoft News, MSN Weather", output)

    def test_applying_requires_explicit_typed_confirmation(self):
        _, _, invoke = self.run_menu(["3", "location", "APPLY", "0"])
        self.assertEqual(
            invoke.call_args.args[0], ["privacy", "set", "location", "--apply", "--yes"]
        )

    def test_failed_preview_never_offers_apply(self):
        invoke = Mock(return_value=1)
        self.run_menu(["7", "0"], invoke)
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(invoke.call_args.args[0], ["recall", "disable"])

    def test_empty_selection_cancels_and_options_cannot_be_injected(self):
        for value in ("", "news --apply", "--yes"):
            answers = ["2", "", "0"] if not value else ["2", value, "0", "0"]
            _, _, invoke = self.run_menu(answers)
            invoke.assert_not_called()

    def test_invalid_selection_can_be_corrected_without_reopening_picker(self):
        _, output, invoke = self.run_menu(["2", "999", "1 3-4", "", "0"])
        self.assertIn("Invalid selection", output)
        invoke.assert_called_once_with(["remove", "news", "solitaire", "clipchamp"])

    def test_numbered_select_all_previews_every_supported_app_before_apply(self):
        _, _, invoke = self.run_menu(["2", str(len(CATALOG) + 1), "APPLY", "0"])
        command = ["remove", *(app.id for app in CATALOG)]
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            [command, [*command, "--apply", "--yes"]],
        )

    def test_cancel_returns_to_main_menu_without_a_removal_preview(self):
        _, _, invoke = self.run_menu(["2", "0", "10", "0"])
        invoke.assert_called_once_with(["report"])

    def test_scoped_startup_names_with_spaces_are_preserved(self):
        _, _, invoke = self.run_menu(["4", '"user:My App"', "", "0"])
        self.assertEqual(invoke.call_args.args[0], ["startup", "disable", "user:My App"])

    def test_restore_path_with_spaces_stays_one_argument(self):
        _, _, invoke = self.run_menu(["8", r"C:\My Backups\settings.json", "", "0"])
        self.assertEqual(invoke.call_args.args[0], ["restore", r"C:\My Backups\settings.json"])

    def test_eof_and_interrupt_exit_cleanly(self):
        for error in (EOFError(), KeyboardInterrupt()):
            self.assertEqual(self.run_menu([error])[0], 130)

    def test_help_does_not_exit_menu_and_read_only_actions_work(self):
        invoke = Mock(side_effect=[0, 0, SystemExit(0)])
        self.run_menu(["1", "10", "11", "0"], invoke)
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list], [["scan"], ["report"], ["--help"]]
        )

    def test_invalid_quotes_and_cancelled_paths_do_not_execute_changes(self):
        self.run_menu(["4", '"unclosed', "8", "", "9", "--apply", "0"])

    def test_saved_profile_and_background_selection_are_previewed(self):
        _, _, invoke = self.run_menu(
            ["9", '"my profile.json"', "", "5", "Example_publisher", "", "6", "", "0"]
        )
        self.assertIn(
            unittest.mock.call(["profile", "run", "my profile.json"]), invoke.call_args_list
        )
        self.assertIn(
            unittest.mock.call(["background", "disable", "Example_publisher"]),
            invoke.call_args_list,
        )

    def test_interactive_no_arguments_opens_menu_but_pipes_show_help(self):
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
    def test_numbers_commas_ranges_and_duplicates_follow_display_order(self):
        self.assertEqual(parse_app_selection("4, 1 2-3,2"), [app.id for app in CATALOG[:4]])
        self.assertEqual(parse_app_selection("8"), [CATALOG[-1].id])

    def test_select_all_accepts_the_number_and_readable_aliases(self):
        for choice in (str(len(CATALOG) + 1), "A", "all", "Select All", " ALL "):
            with self.subTest(choice=choice):
                self.assertEqual(parse_app_selection(choice), [app.id for app in CATALOG])

    def test_empty_and_zero_cancel(self):
        for choice in ("", " ", "0"):
            self.assertEqual(parse_app_selection(choice), [])

    def test_invalid_input_never_partially_selects_apps(self):
        for choice in (
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
            "9999999999999999999999",
        ):
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                parse_app_selection(choice)


class RemovalMenuFlowTests(unittest.TestCase):
    def test_number_selection_drives_existing_preview_without_removing_apps(self):
        from test_app import FakeBackend

        backend = FakeBackend([Package("Microsoft.BingWeather", "weather_1", "installed")])
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("builtins.input", side_effect=["2", "2", "", "0"]),
        ):
            self.assertEqual(main(["menu"], backend=backend), 0)
        self.assertIn("weather_1", output.getvalue())
        self.assertEqual(backend.removed, [])

    def test_select_all_applies_only_detected_supported_apps_after_confirmation(self):
        from test_app import FakeBackend

        packages = [
            Package("Microsoft.BingNews", "news_1", "installed"),
            Package("Microsoft.BingWeather", "weather_1", "provisioned"),
        ]
        backend = FakeBackend(packages)
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.chdir(directory),
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("builtins.input", side_effect=["2", "all", "APPLY", "0"]),
        ):
            self.assertEqual(main(["menu"], backend=backend), 0)
        self.assertEqual(backend.removed, packages)
        self.assertIn("Selected 8 apps", output.getvalue())
