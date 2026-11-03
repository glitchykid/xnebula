import contextlib
import io
import unittest
from unittest.mock import patch

from xnebula.checklist import select_items
from xnebula.console import color_enabled, enable_virtual_terminal, paint


class ConsoleTests(unittest.TestCase):
    def test_colors_only_appear_in_supported_interactive_terminals(self):
        with patch("xnebula.console.color_enabled", return_value=True):
            self.assertIn("\x1b[", paint("Ready", "success"))
        with patch("xnebula.console.color_enabled", return_value=False):
            self.assertEqual(paint("Ready", "success"), "Ready")

    def test_captured_output_and_no_color_remain_readable(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(paint("Warning", "warning"), "Warning")
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            self.assertEqual(paint("Error", "error"), "Error")

    def test_dumb_terminal_displays_plain_text_without_enabling_terminal_modes(self):
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.dict("os.environ", {"TERM": "dumb"}, clear=True),
            patch("xnebula.console.enable_virtual_terminal", return_value=True) as enable,
        ):
            self.assertEqual(paint("Ready", "success"), "Ready")
            enable.assert_not_called()

    def test_capable_or_unspecified_terminal_retains_color(self):
        for environment in ({}, {"TERM": "xterm-256color"}):
            with (
                self.subTest(environment=environment),
                patch("sys.stdout.isatty", return_value=True),
                patch.dict("os.environ", environment, clear=True),
                patch("xnebula.console.enable_virtual_terminal", return_value=True),
            ):
                self.assertIn("\x1b[", paint("Ready", "success"))

    def test_dumb_terminal_rejects_checklist_before_printing_control_sequences(self):
        output = io.StringIO()
        with (
            patch.object(output, "isatty", return_value=True),
            patch.dict("os.environ", {"TERM": "dumb"}, clear=True),
            patch("xnebula.console.ctypes.windll.kernel32", create=True) as kernel,
            contextlib.redirect_stdout(output),
        ):
            self.assertFalse(enable_virtual_terminal())
            with self.assertRaisesRegex(OSError, "does not support"):
                select_items(["One"])
            kernel.GetConsoleMode.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    def test_virtual_terminal_support_is_enabled_for_a_windows_console(self):
        from unittest.mock import Mock

        kernel = Mock()
        kernel.GetConsoleMode.return_value = 1
        kernel.SetConsoleMode.return_value = 1
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("sys.platform", "win32"),
            patch("ctypes.windll.kernel32", kernel, create=True),
            patch.dict("os.environ", {}, clear=True),
        ):
            self.assertTrue(color_enabled())
            kernel.SetConsoleMode.assert_called_once()
            kernel.GetConsoleMode.return_value = 0
            self.assertFalse(color_enabled())
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("sys.platform", "linux"),
            patch.dict("os.environ", {}, clear=True),
        ):
            self.assertTrue(color_enabled())
