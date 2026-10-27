"""Durable, local snapshots shared by native Windows operations."""

import json
import os
from datetime import UTC, datetime
from uuid import uuid4


def save_snapshot(kind, identity, payload, directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{kind}-{uuid4().hex}.json"
    document = {
        "schema": 1,
        "kind": kind,
        "identity": identity,
        "time": datetime.now(UTC).isoformat(),
        **payload,
    }
    with path.open("x", encoding="utf-8") as file:
        json.dump(document, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    print(f"Backup: {path.resolve()}")
    return path


def read_snapshot(path, kind, identity):
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") != 1
        or document.get("kind") != kind
        or document.get("identity") != identity
    ):
        raise ValueError("Backup is invalid or belongs to a different machine/account.")
    return document
