import hashlib
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_portable", ROOT / "scripts/build_portable.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.runtime = self.directory / "runtime.zip"
        with zipfile.ZipFile(self.runtime, "w") as archive:
            for name in (
                "python.exe",
                "python315.dll",
                "python315.zip",
                "python315._pth",
                "LICENSE.txt",
            ):
                archive.writestr(name, b"fixture")

    def build(self):
        digest = hashlib.sha256(self.runtime.read_bytes()).hexdigest()
        with patch.object(builder, "PYTHON_SHA256", digest):
            return builder.build(ROOT, self.runtime, self.directory / "dist")

    def test_archive_contains_launchers_runtime_source_and_license_without_local_data(self):
        path = self.build()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertIn("XNebula/Start-XNebula.cmd", names)
            self.assertIn("XNebula/Start-XNebula-Admin.cmd", names)
            self.assertIn("XNebula/.runtime/LICENSE.txt", names)
            self.assertIn("XNebula/src/xnebula/menu.py", names)
            self.assertIn(b"../src", archive.read("XNebula/.runtime/python315._pth"))
            self.assertFalse(
                any(
                    ".tools/" in name or "__pycache__" in name or ".xnebula/" in name
                    for name in names
                )
            )
        self.assertIn(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.with_suffix(".zip.sha256").read_text(),
        )

    def test_modified_runtime_is_rejected_without_creating_output(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            builder.build(ROOT, self.runtime, self.directory / "dist")
        self.assertFalse((self.directory / "dist").exists())

    def test_unsafe_archive_paths_and_missing_runtime_files_are_rejected(self):
        with zipfile.ZipFile(self.runtime, "a") as archive:
            archive.writestr("../escape", "invalid")
        with self.assertRaises(ValueError):
            self.build()
        with zipfile.ZipFile(self.runtime, "w") as archive:
            archive.writestr("python.exe", "incomplete")
        with self.assertRaises(ValueError):
            self.build()
