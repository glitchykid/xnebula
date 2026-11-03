"""Verify search and selection editing through the real menu and removal planner."""

import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

from test_app import FakeBackend

from xnebula.cli import main
from xnebula.core import Package


class SelectionWorkflowTests(unittest.TestCase):
    def run_workflow(self, confirmation):
        news = Package("Microsoft.BingNews", "news_1", "installed")
        xbox = Package("Microsoft.GamingApp", "xbox_1", "installed")
        overlay = Package("Microsoft.XboxGamingOverlay", "overlay_1", "installed")
        backend = FakeBackend([news, xbox, overlay])
        # Select News, filter Xbox, select matches, then edit and uncheck the last item.
        keys = [" ", "/", "x", "b", "o", "x", "enter", "a", "enter", "end", " ", "enter"]
        output = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.chdir(directory),
            contextlib.redirect_stdout(output),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
            patch("xnebula.menu.enable_virtual_terminal", return_value=True),
            patch("xnebula.checklist.enable_virtual_terminal", return_value=True),
            patch("xnebula.checklist.render_frame"),
            patch("xnebula.checklist.read_key", side_effect=keys),
            patch("builtins.input", side_effect=["1", "EDIT", confirmation, "0"]),
        ):
            self.assertEqual(main(["menu"], backend=backend), 0)
        return backend, output.getvalue(), [news, xbox]

    def test_search_and_edit_only_remove_the_final_reviewed_selection(self):
        backend, output, expected = self.run_workflow("APPLY")
        self.assertEqual(backend.removed, expected)
        self.assertEqual(output.count("Preview: remove Windows apps"), 3)
        self.assertIn("[DONE]", output)

    def test_cancelling_the_edited_preview_never_removes_packages(self):
        backend, output, _ = self.run_workflow("")
        self.assertEqual(backend.removed, [])
        self.assertEqual(output.count("Preview: remove Windows apps"), 2)
        self.assertIn("[CANCELLED]", output)
