"""Terminal commands for reversible Windows configuration."""

from pathlib import Path

from xnebula.registry import WindowsRegistry
from xnebula.settings import (
    SETTINGS,
    apply_changes,
    plan_background,
    plan_settings,
    plan_startup,
    restore_plan,
)


def mutation_options(command):
    command.add_argument("--apply", action="store_true", help="Apply the previewed changes.")
    command.add_argument("--yes", action="store_true", help="Skip the typed confirmation.")
    command.add_argument("--log-dir", type=Path, default=Path(".xnebula/logs"))


def add_commands(commands):
    for group in ("privacy", "storage", "recall", "startup", "background"):
        root = commands.add_parser(group, help=f"Inspect and configure {group}.")
        sub = root.add_subparsers(dest="action", required=True)
        sub.add_parser("list", help="List settings or discover entries.")
        verb = {"privacy": "set", "storage": "configure"}.get(group, "disable")
        change = sub.add_parser(verb, allow_abbrev=False)
        if group in ("privacy", "startup", "background"):
            change.add_argument(
                "ids", nargs="+", help="Exact IDs from list; privacy also accepts all."
            )
        if group == "storage":
            change.add_argument(
                "--downloads-days",
                type=int,
                default=0,
                help="0 keeps Downloads; 1-365 opts into deletion after that many unused days.",
            )
            change.add_argument(
                "--recycle-days",
                type=int,
                default=0,
                help="0 keeps Recycle Bin items; 1-365 opts into permanent deletion.",
            )
        mutation_options(change)
    restore = commands.add_parser("restore", help="Preview restoring a settings/startup backup.")
    restore.add_argument("backup", type=Path)
    mutation_options(restore)


def handle(args, registry=None):
    if args.command in ("privacy", "storage", "recall") and args.action == "list":
        for key, option in SETTINGS.items():
            if option.group == args.command:
                print(f"{key:22} {option.target.hive:4} {option.effect}")
        print("Policies require Pro/Enterprise/Education. HKCU means the account running XNebula.")
        return 0
    registry = registry if registry is not None else WindowsRegistry()
    if args.command == "startup":
        if args.action == "list":
            for key, target in registry.startup().items():
                print(f"{key}  {registry.read(target)}")
            print("Lists Run registry entries: current account and machine-wide (32/64-bit).")
            return 0
        changes = plan_startup(args.ids, registry)
    elif args.command == "background":
        if args.action == "list":
            for family in registry.background_apps():
                print(family)
            return 0
        changes = plan_background(args.ids, registry)
        print("Selected packaged apps may stop background notifications and syncing.")
    elif args.command == "restore":
        changes = restore_plan(args.backup, registry)
    else:
        changes, skipped = plan_settings(
            args.command,
            getattr(args, "ids", ["all"]),
            registry,
            downloads_days=getattr(args, "downloads_days", 0),
            recycle_days=getattr(args, "recycle_days", 0),
        )
        for reason in skipped:
            print(f"Unsupported: {reason}")
    print(f"Preview: {len(changes)} registry value change(s)")
    for change in changes:
        if change.label in SETTINGS:
            print(SETTINGS[change.label].effect)
        print(f"  {change.label}: {change.target.hive}\\{change.target.key} [{change.target.name}]")
        print(f"    {change.before} -> {change.after}")
    if not changes:
        print("Nothing to change.")
        return 0
    if not args.apply:
        print("No changes made. Add --apply to continue.")
        return 0
    if not args.yes and input("Type APPLY to continue: ").strip() != "APPLY":
        print("Cancelled. No changes made.")
        return 0
    apply_changes(changes, registry, args.log_dir)
    print("Registry values verified. Sign out or restart for policy changes to take effect.")
    return 0
