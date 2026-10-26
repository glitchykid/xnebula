import json
import tempfile
import unittest
from pathlib import Path

from xnebula.settings import (
    SETTINGS,
    Change,
    RegistryValue,
    apply_changes,
    plan_settings,
    plan_startup,
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

    def startup(self):
        from xnebula.settings import STARTUP_KEYS, Target

        return {"user:Example": Target("HKCU", STARTUP_KEYS["user"][1], "Example")}


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
        self.assertTrue(plan_settings("recall", ["all"], registry)[1])

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

    def test_startup_disable_preserves_command_for_restore(self):
        registry = MemoryRegistry()
        target = registry.startup()["user:Example"]
        registry.values[target] = RegistryValue(2, r"%LOCALAPPDATA%\Example.exe")
        changes = plan_startup(["user:Example"], registry)
        self.assertEqual(changes, [Change(target, registry.values[target], None, "user:Example")])
        with self.assertRaises(ValueError):
            plan_startup(["*"], registry)
