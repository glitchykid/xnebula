"""Compact numbered interface for the app's Windows-only actions."""

import sys
from pathlib import Path

from xnebula import __version__
from xnebula.backup_picker import choose_backup
from xnebula.checklist import select_items
from xnebula.console import enable_virtual_terminal, paint
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


def choose_items(rows, prefix, title, *, selected=None):
    print(paint("\n" + title, "title"))
    if not rows:
        print("Nothing available to change.")
        return None
    previous = [index for index, row in enumerate(rows) if selected and row[0] in selected]
    if sys.stdin.isatty() and sys.stdout.isatty() and enable_virtual_terminal():
        options = {"selected": previous} if selected is not None else {}
        indexes = select_items([name for _, name, _ in rows], **options)
        if indexes:
            print(paint("Selected: " + ", ".join(rows[index][1] for index in indexes), "title"))
        return [*prefix, *(rows[index][0] for index in indexes)] if indexes else None
    for number, (_, name, _) in enumerate(rows, start=1):
        marker = " [x]" if number - 1 in previous else ""
        print(paint(f"{number:2}", "number") + f"  {name}{marker}")
    print(paint(f"{len(rows) + 1:2}", "number") + f"  Select All ({len(rows)} items)")
    print(" 0  Back")
    while True:
        prompt = (
            "Choose replacement numbers (1,3-5), all, Enter to keep selection, or 0 to cancel: "
            if previous
            else "Choose numbers (1,3-5), Select All, or Enter to go back: "
        )
        raw = input(prompt)
        try:
            indexes = previous if previous and not raw.strip() else parse_numbers(raw, len(rows))
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


def review_command(invoke, command, can_apply, picker=None):
    while command:
        if call(invoke, command) != 0:
            print(paint("[FAILED] Preview failed. Check the details above.", "error"))
            return
        if not can_apply():
            print("No changes to apply.")
            return
        while True:
            edit_hint = "EDIT to change selection, " if picker else ""
            confirmation = input(
                paint(
                    f"Preview only. Type APPLY to continue, {edit_hint}or Enter to go back: ",
                    "warning",
                )
            ).strip()
            if not confirmation:
                print("[CANCELLED] No changes applied.")
                return
            if confirmation == "APPLY":
                result = call(invoke, [*command, "--apply", "--yes"])
                if result == 0:
                    print(paint("[DONE] Operation completed. See the details above.", "success"))
                else:
                    print(
                        paint(
                            "[FAILED] Operation failed or partially completed. See details above.",
                            "error",
                        )
                    )
                return
            if confirmation == "EDIT" and picker:
                rows, prefix, title = picker
                command = choose_items(rows, prefix, title, selected=command[len(prefix) :])
                if not command:
                    print("[CANCELLED] No changes applied.")
                break
            print(paint("Type APPLY exactly, or press Enter to cancel.", "warning"))


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
                picker = None
                if choice == "1":
                    print("Scanning removable Windows apps...", flush=True)
                    apps = apps_provider() if apps_provider is not None else CATALOG
                    picker = (
                        [(app.id, app.title, app.impact) for app in apps],
                        ["remove"],
                        "Removable Windows apps (all accounts)",
                    )
                elif choice == "2":
                    picker = (
                        [(service.name, service.title, service.effect) for service in SERVICES],
                        ["services", "disable"],
                        "Optional services",
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
                if picker:
                    command = choose_items(*picker)
                if command:
                    review_command(invoke, command, can_apply, picker)
            except (BackendError, OSError, ValueError) as error:
                print(paint(f"[ERROR] {error}", "error"))
    except EOFError, KeyboardInterrupt:
        print("\nClosed. Check the latest backup if an operation was interrupted.")
        return 130
