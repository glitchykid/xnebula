"""Small terminal guide that reuses the tested command-line workflows."""

import shlex

from xnebula import __version__
from xnebula.core import CATALOG

MENU = """
 1  Scan installed apps       2  Remove selected apps
 3  Privacy settings         4  Startup entries
 5  Background apps          6  Storage cleanup settings
 7  Disable Recall           8  Restore a settings backup
 9  Run a saved profile     10  Change reports
11  Command help             0  Exit
"""


def call(invoke, command):
    try:
        return invoke(command)
    except SystemExit as error:
        # argparse help and validation must not close the interactive menu.
        return error.code or 0


def selected_command(invoke, category, listing, prefix):
    call(invoke, listing)
    raw = input(f"{category} (space-separated; quote names with spaces; Enter cancels): ").strip()
    if not raw:
        return None
    try:
        values = shlex.split(raw)
    except ValueError:
        print("Unclosed quote. Return to the menu and try again.")
        return None
    if not values or any(value.startswith("-") for value in values):
        print("Enter IDs only; command flags are not accepted here.")
        return None
    return [*prefix, *values]


def parse_app_selection(raw):
    raw = raw.strip()
    if not raw or raw == "0":
        return []
    if raw.casefold() in ("a", "all", "select all", str(len(CATALOG) + 1)):
        return [app.id for app in CATALOG]
    tokens = raw.replace(",", " ").split()
    if not tokens:
        raise ValueError("Enter app numbers or Select All.")
    numbers = set()
    for token in tokens:
        parts = token.split("-")
        if len(parts) not in (1, 2) or any(
            not part.isascii() or not part.isdecimal() for part in parts
        ):
            raise ValueError("Enter app numbers or ranges, such as 1,3-5.")
        start, end = int(parts[0]), int(parts[-1])
        if not 1 <= start <= end <= len(CATALOG):
            raise ValueError(f"App numbers must be between 1 and {len(CATALOG)}.")
        numbers.update(range(start, end + 1))
    return [CATALOG[number - 1].id for number in sorted(numbers)]


def selected_app_command():
    print("\nChoose apps to uninstall (absent apps will be skipped):")
    for number, app in enumerate(CATALOG, start=1):
        print(f"{number:2}  {app.title} - {app.impact}")
    print(f"{len(CATALOG) + 1:2}  Select All ({len(CATALOG)} apps)")
    print(" 0  Back")
    while True:
        raw = input("Select numbers (1 3 5, 1,3,5, or 2-4); Enter cancels: ")
        try:
            ids = parse_app_selection(raw)
        except ValueError:
            print(
                f"Invalid selection. Use 1-{len(CATALOG)}, "
                f"{len(CATALOG) + 1} for Select All, or 0 to go back."
            )
            continue
        if not ids:
            return None
        titles = [app.title for app in CATALOG if app.id in ids]
        print(f"Selected {len(ids)} apps: {', '.join(titles)}")
        return ["remove", *ids]


def run_menu(invoke):
    print(f"XNebula {__version__} | Windows debloating and privacy")
    print("System-wide actions need Start-XNebula-Admin.cmd or administrator PowerShell.")
    try:
        while True:
            print(MENU)
            choice = input("Choose a number: ").strip()
            if choice == "0":
                return 0
            if choice in ("1", "10", "11"):
                call(invoke, {"1": ["scan"], "10": ["report"], "11": ["--help"]}[choice])
                continue
            selections = {
                "3": ("Privacy IDs, or all", ["privacy", "list"], ["privacy", "set"]),
                "4": ("Startup IDs", ["startup", "list"], ["startup", "disable"]),
                "5": ("Package families", ["background", "list"], ["background", "disable"]),
            }
            if choice == "2":
                command = selected_app_command()
            elif choice in selections:
                command = selected_command(invoke, *selections[choice])
            elif choice in ("6", "7"):
                command = {"6": ["storage", "configure"], "7": ["recall", "disable"]}[choice]
            elif choice in ("8", "9"):
                path = input("JSON file path (Enter cancels): ").strip().strip('"')
                command = None
                if path and not path.startswith("-"):
                    command = ["restore", path] if choice == "8" else ["profile", "run", path]
            else:
                print("Choose a number from 0 to 11.")
                continue
            if not command or call(invoke, command) != 0:
                continue
            confirmation = input("Preview only. Type APPLY to make changes, or Enter to go back: ")
            if confirmation.strip() == "APPLY":
                call(invoke, [*command, "--apply", "--yes"])
    except EOFError, KeyboardInterrupt:
        print("\nClosed the menu. Review change reports if an operation was interrupted.")
        return 130
