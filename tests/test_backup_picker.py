import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xnebula.backup_picker import choose_backup, discover_backups


class BackupPickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def backup(self, name, *, kind=None, time=None, modified=1_700_000_000):
        path = self.directory / name
        document = {"schema": 1, "kind": kind, "changes": [], "identity": "SECRET"}
        if time is not None:
            document["time"] = time
        path.write_text(json.dumps(document), encoding="utf-8")
        os.utime(path, (modified, modified))
        return path

    def choose(self, answers):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("builtins.input", side_effect=answers),
        ):
            result = choose_backup(self.directory)
        return result, output.getvalue()

    def test_embedded_aware_time_orders_backups_even_after_copying(self):
        old = self.backup(
            "copied.json",
            kind="services",
            time="2025-01-01T12:00:00+00:00",
            modified=1_800_000_000,
        )
        new = self.backup(
            "new.json",
            kind="animations",
            time="2025-01-02T12:00:00+00:00",
            modified=1_600_000_000,
        )
        rows, skipped = discover_backups(self.directory)
        self.assertEqual([path for path, _ in rows], [new, old])
        self.assertEqual(skipped, 0)

    def test_missing_invalid_and_naive_times_use_file_modified_time(self):
        for time in (None, "invalid", "2025-01-01T12:00:00", 123, []):
            with self.subTest(time=time):
                legacy = self.backup("legacy.json", time=time, modified=1_800_000_000)
                older = self.backup("older.json", modified=1_700_000_000)
                rows, skipped = discover_backups(self.directory)
                self.assertEqual([path for path, _ in rows], [legacy, older])
                self.assertEqual(skipped, 0)

    def test_aware_timestamps_are_compared_as_instants_across_time_zones(self):
        older = self.backup("older.json", kind="services", time="2025-01-01T13:00:00+03:00")
        newer = self.backup("newer.json", kind="services", time="2025-01-01T11:00:00+00:00")
        rows, _ = discover_backups(self.directory)
        self.assertEqual([path for path, _ in rows], [newer, older])

    def test_names_distinguish_backups_with_the_same_kind_and_timestamp(self):
        first = self.backup("first.json", kind="services")
        second = self.backup("second.json", kind="services")
        _, output = self.choose([""])
        self.assertIn(first.name, output)
        self.assertIn(second.name, output)
        self.assertIn("Windows services", output)
        self.assertRegex(output, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertNotIn("SECRET", output)

    def test_bad_documents_are_skipped_without_hiding_valid_backups(self):
        good = self.backup("good.json")
        for index, data in enumerate(
            (
                "invalid",
                "[]",
                "null",
                '{"schema":2}',
                '{"schema":true}',
                '{"schema":1,"kind":"unknown"}',
            )
        ):
            (self.directory / f"bad-{index}.json").write_text(data, encoding="utf-8")
        (self.directory / "bad-encoding.json").write_bytes(b"\xff")
        rows, skipped = discover_backups(self.directory)
        self.assertEqual([path for path, _ in rows], [good])
        self.assertEqual(skipped, 7)
        result, output = self.choose(["1"])
        self.assertEqual(result, ["restore", str(good)])
        self.assertIn("Skipped 7 unreadable or invalid backup file(s).", output)

    def test_inaccessible_file_does_not_prevent_other_backups_from_being_selected(self):
        good = self.backup("good.json")
        bad = self.backup("inaccessible.json")
        original = Path.read_text

        def read(path, *args, **kwargs):
            if path == bad:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            rows, skipped = discover_backups(self.directory)
        self.assertEqual([path for path, _ in rows], [good])
        self.assertEqual(skipped, 1)

    def test_disappearing_file_during_stat_does_not_abort_the_list(self):
        good = self.backup("good.json")
        bad = self.backup("disappearing.json")
        original = Path.stat

        def stat(path, *args, **kwargs):
            if path == bad:
                raise FileNotFoundError("gone")
            return original(path, *args, **kwargs)

        with patch.object(Path, "stat", stat):
            rows, skipped = discover_backups(self.directory)
        self.assertEqual([path for path, _ in rows], [good])
        self.assertEqual(skipped, 1)

    def test_all_invalid_files_report_skipped_count_without_prompting(self):
        (self.directory / "broken.json").write_text("invalid", encoding="utf-8")
        result, output = self.choose([])
        self.assertIsNone(result)
        self.assertIn("Skipped 1 unreadable or invalid backup file(s).", output)
        self.assertIn("No readable settings backups available.", output)
        self.assertNotIn("No settings backups found yet.", output)

    def test_empty_or_missing_directory_returns_without_prompting(self):
        for directory in (self.directory, self.directory / "missing"):
            with self.subTest(directory=directory), contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(choose_backup(directory))

    def test_invalid_input_reprompts_and_paths_with_spaces_remain_intact(self):
        path = self.backup("backup with spaces.json")
        result, output = self.choose(["999", "-1", "1-2", "١", "9" * 5000, " 1 "])
        self.assertEqual(result, ["restore", str(path)])
        self.assertEqual(output.count("Choose one of the displayed backup numbers."), 5)

    def test_enter_and_zero_cancel_selection(self):
        self.backup("backup.json")
        for answer in ("", "0", " "):
            with self.subTest(answer=answer):
                self.assertIsNone(self.choose([answer])[0])
