"""64-bit Windows registry access, with platform checks before writes."""

import json
import sys

from xnebula.settings import STARTUP_KEYS, RegistryValue, Target, validate_target
from xnebula.windows import BackendError, WindowsBackend


class WindowsRegistry:
    def __init__(self):
        self.bridge = WindowsBackend()
        import winreg

        self.api = winreg
        self.edition = self._system_value(
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "EditionID"
        )
        self.identity = {
            "machine": self._system_value(r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"),
            "user": self.bridge._run(
                "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value"
            ),
        }

    def _system_value(self, key, name):
        with self.api.OpenKey(
            self.api.HKEY_LOCAL_MACHINE, key, 0, self.api.KEY_READ | self.api.KEY_WOW64_64KEY
        ) as handle:
            return self.api.QueryValueEx(handle, name)[0]

    @property
    def recall_available(self):
        build = sys.getwindowsversion().build
        revision = self._system_value(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "UBR")
        if build < 26100 or (build == 26100 and revision < 3915):
            return False
        return (
            self.bridge._run(
                "$f = @(Get-WindowsOptionalFeature -Online -ErrorAction Stop | "
                "Where-Object FeatureName -eq 'Recall'); "
                "[bool]($f.Count -gt 0 -and $f[0].State -eq 'Enabled')"
            )
            == "True"
        )

    def _hive(self, target):
        return self.api.HKEY_LOCAL_MACHINE if target.hive == "HKLM" else self.api.HKEY_CURRENT_USER

    def read(self, target):
        validate_target(target)
        try:
            with self.api.OpenKey(
                self._hive(target), target.key, 0, self.api.KEY_READ | self.api.KEY_WOW64_64KEY
            ) as handle:
                data, kind = self.api.QueryValueEx(handle, target.name)
                return RegistryValue(kind, data)
        except FileNotFoundError:
            return None

    def write(self, target, value):
        validate_target(target)
        if value is None:
            try:
                with self.api.OpenKey(
                    self._hive(target),
                    target.key,
                    0,
                    self.api.KEY_SET_VALUE | self.api.KEY_WOW64_64KEY,
                ) as handle:
                    self.api.DeleteValue(handle, target.name)
            except FileNotFoundError:
                pass
        else:
            with self.api.CreateKeyEx(
                self._hive(target), target.key, 0, self.api.KEY_SET_VALUE | self.api.KEY_WOW64_64KEY
            ) as handle:
                self.api.SetValueEx(handle, target.name, 0, value.type, value.data)

    def startup(self):
        entries = {}
        for scope, (hive, key) in STARTUP_KEYS.items():
            try:
                root = self.api.HKEY_LOCAL_MACHINE if hive == "HKLM" else self.api.HKEY_CURRENT_USER
                with self.api.OpenKey(
                    root, key, 0, self.api.KEY_READ | self.api.KEY_WOW64_64KEY
                ) as handle:
                    for index in range(self.api.QueryInfoKey(handle)[1]):
                        name, _, _ = self.api.EnumValue(handle, index)
                        if name:
                            entries[f"{scope}:{name}"] = Target(hive, key, name)
            except FileNotFoundError:
                continue
        return entries

    def background_apps(self):
        payload = self.bridge._run(
            "$names = @(Get-AppxPackage -AllUsers -PackageTypeFilter Main -ErrorAction Stop | "
            "Where-Object { -not $_.IsFramework -and -not $_.NonRemovable } | "
            "Select-Object -ExpandProperty PackageFamilyName -Unique); "
            "ConvertTo-Json -InputObject @($names) -Compress"
        )
        try:
            names = json.loads(payload)
            if not isinstance(names, list) or any(
                not isinstance(name, str) or not name for name in names
            ):
                raise ValueError
            return names
        except ValueError as error:
            raise BackendError("Invalid background app inventory.") from error
