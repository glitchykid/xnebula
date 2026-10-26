import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from xnebula.registry import WindowsRegistry
from xnebula.settings import SETTINGS, STARTUP_KEYS, RegistryValue
from xnebula.windows import BackendError


class FakeWinreg:
    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    KEY_WOW64_64KEY = 256

    def __init__(self):
        self.values = {}

    @contextmanager
    def OpenKey(self, hive, key, reserved, access):
        if not access & self.KEY_WOW64_64KEY:
            raise AssertionError("Wrong registry view")
        if (hive, key) not in self.values:
            raise FileNotFoundError
        yield (hive, key)

    @contextmanager
    def CreateKeyEx(self, hive, key, reserved, access):
        self.values.setdefault((hive, key), {})
        yield (hive, key)

    def QueryValueEx(self, handle, name):
        if name not in self.values[handle]:
            raise FileNotFoundError
        return self.values[handle][name]

    def SetValueEx(self, handle, name, reserved, kind, data):
        self.values[handle][name] = (data, kind)

    def DeleteValue(self, handle, name):
        if name not in self.values[handle]:
            raise FileNotFoundError
        del self.values[handle][name]

    def QueryInfoKey(self, handle):
        return (0, len(self.values[handle]), 0)

    def EnumValue(self, handle, index):
        name = list(self.values[handle])[index]
        data, kind = self.values[handle][name]
        return name, data, kind


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = WindowsRegistry.__new__(WindowsRegistry)
        self.registry.api = FakeWinreg()
        self.registry.bridge = Mock()

    def test_reads_writes_and_deletes_values_in_64_bit_view(self):
        for target in (SETTINGS["location"].target, SETTINGS["tailored"].target):
            self.assertIsNone(self.registry.read(target))
            self.registry.write(target, RegistryValue(4, 1))
            self.assertEqual(self.registry.read(target), RegistryValue(4, 1))
            self.registry.write(target, None)
            self.assertIsNone(self.registry.read(target))
            self.registry.write(target, None)
        self.registry.api.values.clear()
        self.registry.write(SETTINGS["location"].target, None)

    def test_startup_includes_both_machine_views_and_current_user(self):
        for hive, key in STARTUP_KEYS.values():
            self.registry.api.values[(hive, key)] = {
                "Example": ("example.exe", 1),
                "": ("ignored", 1),
            }
        self.assertEqual(
            set(self.registry.startup()), {"user:Example", "machine:Example", "machine32:Example"}
        )
        self.registry.api.values.clear()
        self.assertEqual(self.registry.startup(), {})

    def test_initialization_binds_backup_to_machine_and_account(self):
        api = FakeWinreg()
        api.values[("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")] = {
            "EditionID": ("Professional", 1)
        }
        api.values[("HKLM", r"SOFTWARE\Microsoft\Cryptography")] = {"MachineGuid": ("machine", 1)}
        with (
            patch.dict("sys.modules", {"winreg": api}),
            patch("xnebula.registry.WindowsBackend") as bridge,
        ):
            bridge.return_value._run.return_value = "S-1-test"
            registry = WindowsRegistry()
        self.assertEqual(registry.identity, {"machine": "machine", "user": "S-1-test"})
        self.assertEqual(registry.edition, "Professional")

    def test_recall_requires_updated_build_and_enabled_component(self):
        for build, revision, enabled, expected in (
            (22631, 6000, "True", False),
            (26100, 3914, "True", False),
            (26100, 3915, "True", True),
            (26200, 1, "False", False),
        ):
            with (
                patch(
                    "sys.getwindowsversion", return_value=SimpleNamespace(build=build), create=True
                ),
                patch.object(self.registry, "_system_value", return_value=revision),
            ):
                self.registry.bridge._run.return_value = enabled
                self.assertEqual(self.registry.recall_available, expected)

    def test_background_inventory_validates_shapes(self):
        self.registry.bridge._run.return_value = '["Example_publisher"]'
        self.assertEqual(self.registry.background_apps(), ["Example_publisher"])
        for payload in ("", "null", "{}", "[1]", '[""]'):
            self.registry.bridge._run.return_value = payload
            with self.subTest(payload=payload), self.assertRaises(BackendError):
                self.registry.background_apps()
