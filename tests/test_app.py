import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xnebula.cli import main
from xnebula.core import Package, build_plan
from xnebula.windows import BackendError, parse_inventory


def package(kind="installed", protected=False):
    return Package("Microsoft.BingNews", "Microsoft.BingNews_1.0_x64__publisher", kind, protected)


class FakeBackend:
    def __init__(self, packages=None, error=False):
        self.packages = [package(), package("provisioned")] if packages is None else packages
        self.removed = []
        self.error = error

    def inventory(self):
        return self.packages

    def remove(self, item):
        self.removed.append(item)
        if self.error:
            raise BackendError("Access denied")


class PlanTests(unittest.TestCase):
    def test_selected_app_includes_existing_and_future_accounts(self):
        items = [package(), package("provisioned")]
        self.assertEqual(build_plan(["news"], items), items)

    def test_unselected_and_similarly_named_apps_are_excluded(self):
        items = [Package("Microsoft.BingNewsExtra", "other", "installed")]
        self.assertEqual(build_plan(["news"], items), [])

    def test_duplicate_selections_and_packages_are_removed_once(self):
        self.assertEqual(build_plan(["news", "news"], [package(), package()]), [package()])

    def test_unknown_empty_and_wildcard_selections_fail(self):
        for ids in ([], [""], ["*"], ["news", "unknown"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                build_plan(ids, [])

    def test_protected_app_blocks_the_entire_plan(self):
        with self.assertRaisesRegex(ValueError, "protected"):
            build_plan(["news"], [package(), package(protected=True)])


class InventoryTests(unittest.TestCase):
    def test_empty_and_unicode_inventory(self):
        self.assertEqual(parse_inventory("[]"), [])
        payload = [{"name": "应用", "full_name": "应用_1", "kind": "installed", "protected": False}]
        self.assertEqual(parse_inventory(json.dumps(payload))[0].name, "应用")

    def test_malformed_inventory_fails_closed(self):
        for payload in ("", "null", "{}", "not json", "[1]", '[{"name":"x"}]'):
            with self.subTest(payload=payload), self.assertRaises(BackendError):
                parse_inventory(payload)

    def test_invalid_field_types_and_kinds_are_rejected(self):
        row = {"name": "x", "full_name": "x_1", "kind": "installed", "protected": False}
        for key, value in (
            ("name", ""),
            ("full_name", 1),
            ("kind", "other"),
            ("protected", "false"),
        ):
            with self.subTest(key=key), self.assertRaises(BackendError):
                parse_inventory(json.dumps([{**row, key: value}]))


class CliTests(unittest.TestCase):
    def run_cli(self, args, backend=None, answer="REMOVE"):
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
            patch("sys.stdin.isatty", return_value=False),
            patch("builtins.input", return_value=answer),
        ):
            code = main(args, backend=backend or FakeBackend())
        return code, output.getvalue()

    def test_default_removal_is_preview_without_log_or_mutation(self):
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.run_cli(["remove", "news", "--log-dir", directory], backend)
            self.assertEqual(code, 0)
            self.assertIn("Preview", output)
            self.assertEqual(backend.removed, [])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_apply_records_each_action_and_removes_both_scopes(self):
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            code, _ = self.run_cli(
                ["remove", "news", "--apply", "--yes", "--log-dir", directory], backend
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(backend.removed), 2)
            events = [
                json.loads(line)
                for line in next(Path(directory).glob("*.jsonl")).read_text().splitlines()
            ]
            self.assertEqual(
                [event["status"] for event in events],
                ["planned", "started", "removed", "started", "removed"],
            )

    def test_declining_confirmation_makes_no_changes(self):
        backend = FakeBackend()
        self.assertEqual(self.run_cli(["remove", "news", "--apply"], backend, "no")[0], 0)
        self.assertEqual(backend.removed, [])

    def test_yes_without_apply_stays_a_preview(self):
        backend = FakeBackend()
        self.run_cli(["remove", "news", "--yes"], backend)
        self.assertEqual(backend.removed, [])

    def test_failed_app_is_logged_and_remaining_removals_are_attempted(self):
        backend = FakeBackend(error=True)
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.run_cli(
                ["remove", "news", "--apply", "--yes", "--log-dir", directory], backend
            )
            self.assertEqual(code, 1)
            self.assertIn("Access denied", output)
            self.assertEqual(len(backend.removed), 2)
            self.assertIn(
                '"status": "uncertain"', next(Path(directory).glob("*.jsonl")).read_text()
            )

    def test_unwritable_journal_blocks_removal(self):
        backend = FakeBackend()
        with patch("xnebula.cli.Journal", side_effect=OSError("disk full")):
            self.assertEqual(self.run_cli(["remove", "news", "--apply", "--yes"], backend)[0], 1)
        self.assertEqual(backend.removed, [])

    def test_absent_app_reports_no_changes(self):
        self.assertIn("Nothing to remove", self.run_cli(["remove", "news"], FakeBackend([]))[1])

    def test_catalog_and_help_do_not_require_windows(self):
        self.assertIn("news", self.run_cli(["catalog"])[1])
        self.assertIn("usage:", self.run_cli([])[1])

    def test_scan_shows_only_detected_removable_apps(self):
        code, output = self.run_cli(["scan"])
        self.assertEqual(code, 0)
        self.assertIn("news", output)
        self.assertIn("1 removable Windows apps detected", output)

    def test_unknown_selection_is_rejected_before_inventory(self):
        backend = FakeBackend()
        with patch.object(backend, "inventory") as inventory:
            self.assertEqual(self.run_cli(["remove", "*"], backend)[0], 1)
            inventory.assert_not_called()
