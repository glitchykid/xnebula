"""Durable append-only action journals; these are not app-data backups."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class Journal:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex}.jsonl"
        self.file = self.path.open("x", encoding="utf-8")

    def write(self, status: str, **details):
        record = {"time": datetime.now(UTC).isoformat(), "status": status, **details}
        self.file.write(json.dumps(record, ensure_ascii=True) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())

    def close(self):
        self.file.close()
