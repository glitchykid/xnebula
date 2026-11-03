import contextlib
import io
import json
import os
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from xnebula.settings import (
    RUN,
    SETTINGS,
    Change,
    RegistryValue,
    Target,
    apply_changes,
    plan_settings,
    restore_plan,
)


class MemoryRegistry:
    identity = {"machine": "test-machine", "user": "test-user"}
    edition = "Enterprise"
    recall_available = True

    def __init__(self):
        self.values = {}
        self.writes = []
        self.fail = False

    def read(self, target):
        return self.values.get(target)

    def write(self, target, value):
        if self.fail:
            raise OSError("denied")
        self.values[target] = value
        self.writes.append((target, value))


class SettingsTests(unittest.TestCase):
    def test_privacy_plan_covers_selected_controls_and_preserves_stricter_telemetry(self):
        registry = MemoryRegistry()
        registry.values[SETTINGS["diagnostics"].target] = RegistryValue(4, 0)
        plan, skipped = plan_settings("privacy", ["all"], registry)
        self.assertNotIn("diagnostics", [change.label for change in plan])
        self.assertIn("location", [change.label for change in plan])
        self.assertIn("activity-publishing", [change.label for change in plan])
        self.assertEqual(skipped, [])

    def test_unknown_setting_and_mixed_all_are_rejected(self):
        for ids in (["*"], [], ["all", "location"], ["storage-enable"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                plan_settings("privacy", ids, MemoryRegistry())

    def test_home_and_unavailable_recall_are_reported_as_unsupported(self):
        registry = MemoryRegistry()
        registry.edition = "Core"
        plan, skipped = plan_settings("privacy", ["all"], registry)
        self.assertEqual(plan, [])
        self.assertTrue(skipped)
        registry.edition = "Professional"
        registry.recall_available = False
        self.assertTrue(plan_settings("privacy", ["recall-snapshots"], registry)[1])

    def test_backup_precedes_writes_and_restores_absent_and_existing_values(self):
        registry = MemoryRegistry()
        first = SETTINGS["advertising"].target
        registry.values[first] = RegistryValue(4, 0)
        changes, _ = plan_settings("privacy", ["advertising", "location"], registry)
        with tempfile.TemporaryDirectory() as directory:
            backup = apply_changes(changes, registry, Path(directory))
            data = json.loads(backup.read_text())
            self.assertEqual(data["identity"], registry.identity)
            reverse = restore_plan(backup, registry)
            apply_changes(reverse, registry, Path(directory))
            self.assertEqual(registry.values[first], RegistryValue(4, 0))
            self.assertIsNone(registry.values[SETTINGS["location"].target])
            self.assertEqual(restore_plan(backup, registry), [])

    def test_stale_plan_and_failed_backup_make_no_writes(self):
        registry = MemoryRegistry()
        changes, _ = plan_settings("privacy", ["location"], registry)
        registry.values[changes[0].target] = RegistryValue(4, 42)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            apply_changes(changes, registry, Path(directory))
        self.assertEqual(registry.writes, [])

    def test_failed_write_keeps_backup(self):
        registry = MemoryRegistry()
        changes, _ = plan_settings("privacy", ["location"], registry)
        registry.fail = True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                apply_changes(changes, registry, Path(directory))
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)

    def test_restore_rejects_foreign_machine_conflicts_and_arbitrary_registry_paths(self):
        registry = MemoryRegistry()
        changes, _ = plan_settings("privacy", ["location"], registry)
        with tempfile.TemporaryDirectory() as directory:
            backup = apply_changes(changes, registry, Path(directory))
            original = json.loads(backup.read_text())
            registry.values[changes[0].target] = RegistryValue(4, 42)
            with self.assertRaises(ValueError):
                restore_plan(backup, registry)
            for change in ("identity", "target", "type"):
                document = json.loads(json.dumps(original))
                if change == "identity":
                    document["identity"]["machine"] = "another"
                elif change == "target":
                    document["changes"][0]["target"]["key"] = "Software\\Malicious"
                else:
                    document["changes"][0]["after"]["type"] = 99
                backup.write_text(json.dumps(document))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    restore_plan(backup, registry)


class BackupValidationTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.target = SETTINGS["location"].target
        self.change = Change(self.target, None, RegistryValue(4, 1), "location")
        self.path = self.directory / "backup.json"
        self.capture = contextlib.redirect_stdout(io.StringIO())
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def document(self):
        return {"schema": 1, "identity": self.registry.identity, "changes": [asdict(self.change)]}

    def test_restore_rejects_boolean_float_and_missing_schema(self):
        for schema in (True, False, 1.0, "1", None):
            document = self.document()
            document["schema"] = schema
            self.path.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                restore_plan(self.path, self.registry)
        self.assertEqual(self.registry.writes, [])

    def test_restore_rejects_malformed_document_and_change_shapes(self):
        for value in (
            None,
            [],
            1,
            "backup",
            {},
            {"schema": 1},
            {**self.document(), "changes": None},
            {**self.document(), "changes": [None]},
            {**self.document(), "changes": [{"target": []}]},
        ):
            self.path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                restore_plan(self.path, self.registry)

    def test_restore_rejects_duplicate_targets_even_when_already_restored(self):
        document = self.document()
        document["changes"] *= 2
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            restore_plan(self.path, self.registry)
        self.assertEqual(self.registry.writes, [])

    def test_apply_rejects_duplicate_targets_before_backup_or_first_write(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            apply_changes([self.change, self.change], self.registry, self.directory)
        self.assertEqual(self.registry.writes, [])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_apply_rejects_invalid_values_and_labels_before_first_write(self):
        other = Change(SETTINGS["advertising"].target, None, RegistryValue(4, 1), "advertising")
        for invalid in (
            replace(self.change, after=RegistryValue(4, True)),
            replace(self.change, after=RegistryValue(4, -1)),
            replace(self.change, after=RegistryValue(4, 0x1_0000_0000)),
            replace(self.change, after=RegistryValue(7, ["valid", ""])),
            replace(self.change, after=RegistryValue(99, "unsupported")),
            replace(self.change, before=RegistryValue(99, "unsupported")),
            replace(self.change, after={"type": 4, "data": 1}),
            replace(self.change, label=123),
        ):
            self.registry.values[self.target] = invalid.before
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                apply_changes([other, invalid], self.registry, self.directory)
            self.assertEqual(self.registry.writes, [])
            self.assertEqual(list(self.directory.iterdir()), [])

    def test_failed_backup_sync_prevents_registry_writes(self):
        with (
            patch("xnebula.settings.os.fsync", side_effect=OSError("disk full")),
            self.assertRaisesRegex(OSError, "disk full"),
        ):
            apply_changes([self.change], self.registry, self.directory)
        self.assertEqual(self.registry.writes, [])

    def test_case_variations_of_the_same_startup_value_are_duplicate_targets(self):
        first = Change(Target("HKCU", RUN, "ExampleApp"), None, RegistryValue(1, "app.exe"), "app")
        second = replace(first, target=Target("HKCU", RUN, "exampleapp"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            apply_changes([first, second], self.registry, self.directory)
        self.assertEqual(self.registry.writes, [])
        document = {**self.document(), "changes": [asdict(first), asdict(second)]}
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            restore_plan(self.path, self.registry)

    def test_backup_and_started_journal_are_synced_before_registry_write(self):
        original_write = self.registry.write
        with patch("xnebula.settings.os.fsync", wraps=os.fsync) as sync:

            def write(target, value):
                self.assertGreaterEqual(sync.call_count, 3)
                original_write(target, value)

            self.registry.write = write
            path = apply_changes([self.change], self.registry, self.directory)
        self.assertEqual(self.registry.writes, [(self.target, RegistryValue(4, 1))])
        self.assertEqual(json.loads(path.read_text())["changes"], [asdict(self.change)])
