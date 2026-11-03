"""Readable backup selection that tolerates damaged or disappearing files."""

import json
from datetime import datetime

from xnebula.console import paint

BACKUP_LABELS = {
    "services": "Windows services",
    "animations": "Windows animations",
    None: "Privacy / registry settings",
}


def _backup_time(document, modified):
    try:
        created = datetime.fromisoformat(document.get("time"))
        if created.tzinfo is not None and created.utcoffset() is not None:
            return created.astimezone()
    except TypeError, ValueError, OverflowError, OSError:
        pass
    return datetime.fromtimestamp(modified).astimezone()


def discover_backups(directory):
    rows, skipped = [], 0
    for path in directory.glob("*.json"):
        try:
            modified = path.stat().st_mtime
            document = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or type(document.get("schema")) is not int
                or document["schema"] != 1
                or document.get("kind") not in BACKUP_LABELS
            ):
                skipped += 1
                continue
            when = _backup_time(document, modified)
            label = BACKUP_LABELS[document.get("kind")]
            title = f"{when:%Y-%m-%d %H:%M:%S}  {label}  {path.name}"
            rows.append((when, path, title))
        except OSError, ValueError, TypeError, OverflowError:
            skipped += 1
    rows.sort(key=lambda row: (row[0], row[1].name), reverse=True)
    return [(path, title) for _, path, title in rows], skipped


def choose_backup(directory):
    rows, skipped = discover_backups(directory)
    if skipped:
        print(paint(f"Skipped {skipped} unreadable or invalid backup file(s).", "warning"))
    if not rows:
        print(
            "No readable settings backups available."
            if skipped
            else "No settings backups found yet."
        )
        return None
    print(paint("Restore a backup (newest first; local time)", "title"))
    for number, (_, title) in enumerate(rows, start=1):
        print(f"{number:2}  {title}")
    while True:
        raw = input("Backup number, or Enter to go back: ").strip()
        if not raw or raw == "0":
            return None
        try:
            number = int(raw) if raw.isascii() and raw.isdecimal() else 0
        except ValueError:
            number = 0
        if 1 <= number <= len(rows):
            return ["restore", str(rows[number - 1][0])]
        print(paint("Choose one of the displayed backup numbers.", "warning"))
