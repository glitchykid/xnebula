"""Exercise an actual built portable ZIP without performing Windows mutations."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from xnebula import __version__

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "dist" / f"xnebula-{__version__}-windows-x64.zip"


@unittest.skipUnless(sys.platform == "win32" and ARCHIVE.exists(), "Build the portable ZIP first")
class PortableLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name) / "Portable space & apostrophe's (test)"
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(cls.directory)
        cls.app = cls.directory / "XNebula"
        cls.ps = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"

    def run_launcher(self, args, *, input=None):
        return subprocess.run(
            [
                str(self.ps),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.app / "scripts/launch.ps1"),
                *args,
            ],
            input=input,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=self.directory,
        )

    def test_portable_version_and_menu_run_without_installed_python(self):
        result = self.run_launcher(["--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)
        result = self.run_launcher([], input="0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Choose a number", result.stdout)

    def test_batch_launcher_works_from_another_directory_with_special_characters(self):
        launcher = self.app / "Start-XNebula.cmd"
        command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{launcher}" --version"'
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=self.directory,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)

    def test_arguments_with_spaces_survive_and_data_stays_in_app_folder(self):
        result = self.run_launcher(
            [
                "profile",
                "save",
                "my profile.json",
                "--startup",
                "user:My App",
                "--privacy",
                "location",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = json.loads((self.app / "my profile.json").read_text())
        self.assertEqual(profile["startup"], ["user:My App"])
        self.assertFalse((self.directory / "my profile.json").exists())

    def test_invalid_command_returns_exit_code_without_uninstalling_anything(self):
        self.assertEqual(self.run_launcher(["not-a-command"]).returncode, 2)

    def test_missing_runtime_has_an_actionable_error(self):
        empty = self.directory / "incomplete"
        (empty / "scripts").mkdir(parents=True)
        script = empty / "scripts/launch.ps1"
        script.write_bytes((self.app / "scripts/launch.ps1").read_bytes())
        result = subprocess.run(
            [
                str(self.ps),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "--version",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Extract the complete", result.stderr)

    def test_elevation_payload_preserves_arguments_without_running_them_as_code(self):
        script = ROOT / "scripts/launch.ps1"
        fake = self.directory / "capture.ps1"
        fake.write_text(
            "param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Values=@())\n"
            "ConvertTo-Json -InputObject @($Values) -Compress\nexit 37\n"
        )

        def literal(value):
            return "'" + str(value).replace("'", "''") + "'"

        values = ["profile", "my profile.json", "user:App 'Quoted' & $HOME"]
        command = (
            f". {literal(script)}; New-XNebulaElevationCommand -ScriptPath {literal(fake)} "
            f"-AppArguments @({','.join(literal(v) for v in values)})"
        )
        encoded = subprocess.run(
            [str(self.ps), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            input="",
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(encoded.returncode, 0, encoded.stderr)
        result = subprocess.run(
            [
                str(self.ps),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded.stdout.strip(),
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(json.loads(result.stdout), values)
