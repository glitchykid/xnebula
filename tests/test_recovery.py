import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xnebula.recovery import read_snapshot, save_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.identity = {"machine": "test-machine", "user": "test-user"}
        self.path = self.directory / "backup.json"

    def document(self):
        return {"schema": 1, "kind": "services", "identity": self.identity, "changes": []}

    def test_read_rejects_boolean_and_float_schema_versions(self):
        for schema in (True, False, 1.0, "1", None):
            document = {**self.document(), "schema": schema}
            self.path.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                read_snapshot(self.path, "services", self.identity)

    def test_read_rejects_bad_shapes_foreign_identity_and_wrong_kind(self):
        for document in (
            None,
            [],
            1,
            "backup",
            {},
            {**self.document(), "identity": {"machine": "other", "user": "other"}},
            {**self.document(), "kind": "animations"},
        ):
            self.path.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(document=document), self.assertRaises(ValueError):
                read_snapshot(self.path, "services", self.identity)

    def test_saved_snapshot_round_trips_after_successful_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            path = save_snapshot("services", self.identity, {"changes": []}, self.directory)
        document = read_snapshot(path, "services", self.identity)
        self.assertEqual(document["changes"], [])
        self.assertIn("time", document)

    def test_failed_sync_does_not_claim_success_or_return_backup(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.recovery.os.fsync", side_effect=OSError("disk full")),
            self.assertRaisesRegex(OSError, "disk full"),
        ):
            save_snapshot("services", self.identity, {"changes": []}, self.directory)
        self.assertNotIn("Backup:", output.getvalue())
