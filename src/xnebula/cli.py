"""PowerShell-friendly terminal commands."""

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from xnebula import __version__, profiles, settings_cli
from xnebula.core import CATALOG, build_plan, selected_apps
from xnebula.journal import Journal
from xnebula.menu import run_menu
from xnebula.windows import BackendError, WindowsBackend


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="xnebula",
        description="Preview Windows app removal, privacy, startup, and cleanup settings.",
        allow_abbrev=False,
    )
    result.add_argument("--version", action="version", version=f"XNebula {__version__}")
    commands = result.add_subparsers(dest="command")
    settings_cli.add_commands(commands)
    profiles.add_commands(commands)
    commands.add_parser("menu", help="Open the guided terminal menu.")
    commands.add_parser("catalog", help="List supported app IDs and removal effects.")
    commands.add_parser(
        "scan", help="Scan installed and provisioned apps (administrator required)."
    )
    remove = commands.add_parser(
        "remove", help="Preview selected apps; use --apply to remove.", allow_abbrev=False
    )
    remove.add_argument("apps", nargs="+", metavar="APP_ID")
    remove.add_argument(
        "--apply", action="store_true", help="Apply system-wide removal after confirmation."
    )
    remove.add_argument(
        "--yes", action="store_true", help="Skip confirmation when combined with --apply."
    )
    remove.add_argument(
        "--log-dir",
        type=Path,
        default=Path(".xnebula/logs"),
        help="Action journal directory (default: .xnebula/logs).",
    )
    return result


def main(argv=None, *, backend=None, registry=None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    if args.command == "menu" or (args.command is None and sys.stdin.isatty()):
        return run_menu(lambda command: main(command, backend=backend, registry=registry))
    if args.command is None:
        arguments.print_help()
        return 0
    if args.command == "catalog":
        for app in CATALOG:
            print(f"{app.id:12} {app.title:24} {app.impact}")
        return 0
    try:
        if args.command in ("privacy", "storage", "recall", "startup", "background", "restore"):
            return settings_cli.handle(args, registry)
        if args.command in ("profile", "report"):
            return profiles.handle(
                args, lambda command: main(command, backend=backend, registry=registry)
            )
        if args.command == "remove":
            selected_apps(args.apps)
        backend = backend if backend is not None else WindowsBackend()
        packages = backend.inventory()
        if args.command == "scan":
            print("Scope: all existing accounts + provisioning for new accounts")
            for app in CATALOG:
                matches = [p for p in packages if p.name.casefold() == app.name.casefold()]
                states = sorted({"protected" if p.protected else p.kind for p in matches})
                print(f"{app.id:12} {app.title:24} {', '.join(states) or 'absent'}")
            return 0
        plan = build_plan(args.apps, packages)
        print("Preview: all existing accounts + provisioning for new accounts")
        for app in selected_apps(args.apps):
            print(f"  {app.title}: {app.impact}")
        for item in plan:
            print(f"  {item.kind:12} {item.full_name}")
        if not plan:
            print("Nothing to remove.")
            return 0
        if not args.apply:
            print("No changes made. Add --apply to remove these packages.")
            return 0
        print("Removal affects every account and may delete app data. The journal is not a backup.")
        if not args.yes and input("Type REMOVE to continue: ").strip() != "REMOVE":
            print("Cancelled. No changes made.")
            return 0
        journal = Journal(args.log_dir)
        try:
            journal.write(
                "planned", scope="all-users-and-provisioning", packages=[asdict(p) for p in plan]
            )
            print(f"Journal: {journal.path.resolve()}")
            for item in plan:
                journal.write("started", package=asdict(item))
                try:
                    backend.remove(item)
                except (BackendError, KeyboardInterrupt) as error:
                    journal.write(
                        "uncertain", package=asdict(item), error=str(error) or "Interrupted"
                    )
                    raise
                journal.write("removed", package=asdict(item))
                print(f"Removed {item.kind}: {item.name}")
        finally:
            journal.close()
        print("Selected removals completed. Run 'xnebula scan' to review remaining apps.")
        return 0
    except (BackendError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        print(
            "Stopped. If changes started, review the journal and scan again before retrying.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt, EOFError:
        print("Cancelled. If changes started, review the journal and scan again.", file=sys.stderr)
        return 130
