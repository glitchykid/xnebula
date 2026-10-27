"""Focused privacy and recovery commands."""

import json
from pathlib import Path

from xnebula.console import paint
from xnebula.registry import WindowsRegistry
from xnebula.settings import SETTINGS, apply_changes, plan_settings, restore_plan


def mutation_options(command):
    command.add_argument("--apply", action="store_true", help="Apply the displayed preview.")
    command.add_argument("--yes", action="store_true", help="Skip the typed confirmation.")
    command.add_argument("--log-dir", type=Path, default=Path(".xnebula/logs"))


def add_commands(commands):
    root = commands.add_parser(
        "privacy", help="Apply supported privacy protections, including Recall."
    )
    sub = root.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    change = sub.add_parser("set", allow_abbrev=False)
    change.add_argument("ids", nargs="*", default=["all"])
    mutation_options(change)
    restore = commands.add_parser(
        "restore", help="Restore a settings, service, or animation backup."
    )
    restore.add_argument("backup", type=Path)
    mutation_options(restore)


def confirm(args):
    return args.yes or input("Type APPLY to continue, or Enter to cancel: ").strip() == "APPLY"


def preview_changes(changes):
    print(paint(f"Preview: {len(changes)} setting change(s)", "title"))
    shown = set()
    for change in changes:
        if change.label not in shown:
            shown.add(change.label)
            option = SETTINGS.get(change.label)
            description = option.effect if option else change.label
            scope = "this account" if change.target.hive == "HKCU" else "all accounts"
            print(f"  - {description} [{scope}]")


def handle(args, registry=None, *, services=None, animations=None, on_preview=None):
    if args.command == "privacy" and args.action == "list":
        for key, option in SETTINGS.items():
            print(f"{key:22} {option.effect}")
        return 0
    if args.command == "restore":
        document = json.loads(args.backup.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Invalid backup file.")
        kind = document.get("kind")
        if kind in ("services", "animations"):
            from xnebula.animations import WindowsAnimations, restore_animations
            from xnebula.services import WindowsServices, restore_services

            if kind == "services":
                manager = services if services is not None else WindowsServices()
                operation = restore_services
            else:
                manager = (
                    animations if animations is not None else WindowsAnimations(registry=registry)
                )
                operation = restore_animations
            changes = operation(args.backup, manager, args.log_dir, apply=False)
            if on_preview is not None:
                on_preview(bool(changes))
            if args.apply and changes and confirm(args):
                operation(args.backup, manager, args.log_dir)
            elif not args.apply:
                print("Preview only. Add --apply to restore.")
            return 0
        if kind is not None:
            raise ValueError("Unsupported backup type.")
    registry = registry if registry is not None else WindowsRegistry()
    if args.command == "restore":
        changes = restore_plan(args.backup, registry)
    else:
        changes, skipped = plan_settings("privacy", args.ids or ["all"], registry)
        for reason in skipped:
            print(paint(f"[SKIP] {reason}", "warning"))
    preview_changes(changes)
    if on_preview is not None:
        on_preview(len(changes))
    if not changes:
        print("Nothing to change.")
        return 0
    if not args.apply:
        print("Preview only. Add --apply to make these changes.")
        return 0
    if not confirm(args):
        print("Cancelled. No changes made.")
        return 0
    apply_changes(changes, registry, args.log_dir)
    print(paint("[OK] Settings saved. Sign out or restart to apply every policy.", "success"))
    return 0
