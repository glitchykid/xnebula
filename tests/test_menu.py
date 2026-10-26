import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from xnebula.cli import main
from xnebula.menu import run_menu


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
        _, _, invoke = self.run_menu(["2", "news weather", "", "0"])
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            [
                ["catalog"],
                ["remove", "news", "weather"],
            ],
        )

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
            _, _, invoke = self.run_menu(["2", value, "0"])
            self.assertEqual(invoke.call_count, 1)
            self.assertEqual(invoke.call_args.args[0], ["catalog"])

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
        self.run_menu(["2", '"unclosed', "8", "", "9", "--apply", "0"])

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
