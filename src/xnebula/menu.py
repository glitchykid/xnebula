"""Compact numbered interface for the app's Windows-only actions."""

import json
from datetime import datetime
from pathlib import Path

from xnebula import __version__
from xnebula.console import paint
from xnebula.core import CATALOG
from xnebula.services import SERVICES
from xnebula.windows import BackendError


def call(invoke, command):
    try:
        return invoke(command)
    except SystemExit as error:
        return error.code or 0


def parse_numbers(raw, count):
    raw = raw.strip()
    if not raw or raw == "0":
        return []
    if raw.casefold() in ("a", "all", "select all", str(count + 1)):
        return list(range(count))
    tokens = raw.replace(",", " ").split()
    if not tokens:
        raise ValueError("Enter numbers or Select All.")
    numbers = set()
    for token in tokens:
        parts = token.split("-")
        if len(parts) not in (1, 2) or any(
            not part.isascii() or not part.isdecimal() for part in parts
        ):
            raise ValueError("Enter numbers or ranges, such as 1,3-5.")
        start, end = int(parts[0]), int(parts[-1])
        if not 1 <= start <= end <= count:
            raise ValueError("Selection is outside the displayed list.")
        numbers.update(range(start - 1, end))
    return sorted(numbers)


def parse_app_selection(raw, apps=CATALOG):
    return [apps[index].id for index in parse_numbers(raw, len(apps))]


def choose_items(rows, prefix, title):
    print(paint("\n" + title, "title"))
    if not rows:
        print("Nothing available to change.")
        return None
    for number, (_, name, effect) in enumerate(rows, start=1):
        print(paint(f"{number:2}", "number") + f"  {name} - {effect}")
    print(paint(f"{len(rows) + 1:2}", "number") + f"  Select All ({len(rows)} items)")
    print(" 0  Back")
    while True:
        raw = input("Choose numbers (1,3-5), Select All, or Enter to go back: ")
        try:
            indexes = parse_numbers(raw, len(rows))
        except ValueError:
            print(
                paint(
                    "Invalid selection. Use the displayed numbers, a range, all, or 0.", "warning"
                )
            )
            continue
        if not indexes:
            return None
        print(paint("Selected: " + ", ".join(rows[index][1] for index in indexes), "title"))
        return [*prefix, *(rows[index][0] for index in indexes)]


def choose_backup(directory):
    rows = []
    labels = {
        "services": "Windows services",
        "animations": "Windows animations",
        None: "Privacy / registry settings",
    }
    for path in sorted(
        directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            kind = data.get("kind")
            if data.get("schema") != 1 or kind not in labels:
                continue
            when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            rows.append((path, f"{when}  {labels[kind]}"))
        except OSError, ValueError, AttributeError:
            continue
    if not rows:
        print("No settings backups found yet.")
        return None
    print(paint("Restore a backup (newest first)", "title"))
    for number, (_, title) in enumerate(rows, start=1):
        print(f"{number:2}  {title}")
    while True:
        raw = input("Backup number, or Enter to go back: ").strip()
        if not raw or raw == "0":
            return None
        if raw.isascii() and raw.isdecimal() and 1 <= int(raw) <= len(rows):
            return ["restore", str(rows[int(raw) - 1][0])]
        print(paint("Choose one of the displayed backup numbers.", "warning"))


def run_menu(
    invoke, *, apps_provider=None, backups_dir=Path(".xnebula/logs"), can_apply=lambda: True
):
    print(paint(f"XNebula {__version__} | Windows cleanup", "title"))
    print("Use Start-XNebula-Admin.cmd for system-wide changes.")
    try:
        while True:
            print(
                "\n"
                + paint("1", "number")
                + "  Remove Windows apps     "
                + paint("2", "number")
                + "  Disable optional services"
            )
            print(
                paint("3", "number")
                + "  Apply privacy settings  "
                + paint("4", "number")
                + "  Disable all Windows animations"
            )
            print(
                paint("5", "number")
                + "  Force uninstall Edge    "
                + paint("6", "number")
                + "  Restore a backup"
            )
            print("0  Exit")
            choice = input("Choose a number: ").strip()
            if choice == "0":
                return 0
            try:
                if choice == "1":
                    apps = apps_provider() if apps_provider is not None else CATALOG
                    command = choose_items(
                        [(app.id, app.title, app.impact) for app in apps],
                        ["remove"],
                        "Removable Windows apps (all accounts)",
                    )
                elif choice == "2":
                    command = choose_items(
                        [(service.name, service.title, service.effect) for service in SERVICES],
                        ["services", "disable"],
                        "Optional services - read the effects before Select All",
                    )
                elif choice in ("3", "4", "5"):
                    command = {
                        "3": ["privacy", "set", "all"],
                        "4": ["animations", "disable"],
                        "5": ["edge", "remove"],
                    }[choice]
                elif choice == "6":
                    command = choose_backup(backups_dir)
                else:
                    print(paint("Choose a number from 0 to 6.", "warning"))
                    continue
                if not command or call(invoke, command) != 0 or not can_apply():
                    continue
                confirmation = input(
                    paint("Preview only. Type APPLY to continue, or Enter to go back: ", "warning")
                )
                if confirmation.strip() == "APPLY":
                    call(invoke, [*command, "--apply", "--yes"])
            except (BackendError, OSError, ValueError) as error:
                print(paint(f"[ERROR] {error}", "error"))
    except EOFError, KeyboardInterrupt:
        print("\nClosed. Check the latest backup if an operation was interrupted.")
        return 130
