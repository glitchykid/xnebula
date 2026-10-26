"""Small terminal guide that reuses the tested command-line workflows."""

import shlex

from xnebula import __version__

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
                "2": ("App IDs", ["catalog"], ["remove"]),
                "3": ("Privacy IDs, or all", ["privacy", "list"], ["privacy", "set"]),
                "4": ("Startup IDs", ["startup", "list"], ["startup", "disable"]),
                "5": ("Package families", ["background", "list"], ["background", "disable"]),
            }
            if choice in selections:
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
