"""Windows app removal, services, privacy, animations, and recovery."""

import argparse
import sys
from dataclasses import asdict

from xnebula import __version__, settings_cli
from xnebula.animations import WindowsAnimations, disable_animations
from xnebula.console import paint
from xnebula.core import CATALOG, available_apps, build_plan, removable_name, selected_apps
from xnebula.edge import WindowsEdge
from xnebula.journal import Journal
from xnebula.menu import run_menu
from xnebula.services import SERVICES, WindowsServices, apply_service_changes, plan_services
from xnebula.settings import RegistryValue
from xnebula.windows import BackendError, WindowsBackend


def parser():
    result = argparse.ArgumentParser(
        prog="xnebula",
        description="Windows app removal, optional services, privacy, and animations.",
        allow_abbrev=False,
    )
    result.add_argument("--version", action="version", version=f"XNebula {__version__}")
    commands = result.add_subparsers(dest="command")
    settings_cli.add_commands(commands)
    commands.add_parser("menu", help="Open the numbered menu.")
    commands.add_parser(
        "catalog", help="List example bundled apps; scan discovers apps on this PC."
    )
    commands.add_parser("scan", help="List removable Windows apps on this PC.")
    remove = commands.add_parser(
        "remove", help="Remove selected app IDs or all removable Windows apps.", allow_abbrev=False
    )
    remove.add_argument("apps", nargs="+", metavar="APP_ID")
    settings_cli.mutation_options(remove)
    services = commands.add_parser("services", help="Disable optional Windows services.")
    sub = services.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    disable = sub.add_parser("disable")
    disable.add_argument("ids", nargs="*", default=["all"])
    settings_cli.mutation_options(disable)
    animations = commands.add_parser("animations", help="Disable Windows-managed animations.")
    animation_sub = animations.add_subparsers(dest="action", required=True)
    settings_cli.mutation_options(animation_sub.add_parser("disable"))
    edge = commands.add_parser(
        "edge", help="Force-mode uninstall through Edge's signed uninstaller."
    )
    edge_sub = edge.add_subparsers(dest="action", required=True)
    settings_cli.mutation_options(edge_sub.add_parser("remove"))
    return result


def apply_requested(args):
    if not args.apply:
        print("Preview only. Add --apply to continue.")
        return False
    if not settings_cli.confirm(args):
        print("Cancelled. No changes made.")
        return False
    return True


def remove_apps(args, backend, on_preview=None):
    packages = backend.inventory()
    if args.command == "scan":
        apps = available_apps(packages)
        for number, app in enumerate(apps, start=1):
            print(f"{number:2}  {app.title:28} {app.id}")
        print(f"{len(apps)} removable Windows apps detected. Essential components are excluded.")
        return 0
    plan = build_plan(args.apps, packages)
    if on_preview is not None:
        on_preview(len(plan))
    print(paint("Preview: remove Windows apps for all existing and new accounts", "title"))
    for app in selected_apps(args.apps, packages):
        print(f"  - {app.title}")
    if any(
        item.name in ("Microsoft.WindowsStore", "Microsoft.DesktopAppInstaller") for item in plan
    ):
        print(
            paint(
                "Removing Store/App Installer can make reinstalling apps harder.",
                "warning",
            )
        )
    if not plan:
        print("Nothing to remove.")
        return 0
    print(
        paint(
            "Running apps may close; unsaved work may be lost. App data is not backed up.",
            "warning",
        )
    )
    if not apply_requested(args):
        return 0
    journal = Journal(args.log_dir)
    failed = 0
    try:
        journal.write(
            "planned", scope="all-users-and-provisioning", packages=[asdict(item) for item in plan]
        )
        print(f"Action log: {journal.path.resolve()}")
        for item in plan:
            journal.write("started", package=asdict(item))
            try:
                backend.remove(item)
            except BackendError as error:
                failed += 1
                journal.write("uncertain", package=asdict(item), error=str(error))
                print(paint(f"[FAILED] {item.name}: {error}", "error"))
                continue
            except KeyboardInterrupt:
                journal.write("uncertain", package=asdict(item), error="Interrupted")
                raise
            journal.write("removed", package=asdict(item))
            print(paint(f"[REMOVED] {item.name} ({item.kind})", "success"))
    finally:
        journal.close()
    print(f"Completed: {len(plan) - failed} package removal(s); {failed} failed.")
    return int(bool(failed))


def main(
    argv=None,
    *,
    backend=None,
    registry=None,
    services=None,
    animations=None,
    edge=None,
    on_preview=None,
):
    arguments = parser()
    args = arguments.parse_args(argv)

    pending = [True]

    def invoke(command):
        pending[0] = True
        return main(
            command,
            backend=backend,
            registry=registry,
            services=services,
            animations=animations,
            edge=edge,
            on_preview=lambda count: pending.__setitem__(0, bool(count)),
        )

    if args.command == "menu" or (args.command is None and sys.stdin.isatty()):
        return run_menu(
            invoke,
            apps_provider=lambda: available_apps(
                (backend if backend is not None else WindowsBackend()).inventory()
            ),
            can_apply=lambda: pending[0],
        )
    if args.command is None:
        arguments.print_help()
        return 0
    try:
        if args.command == "catalog":
            for app in CATALOG:
                print(f"{app.id:12} {app.title:24} {app.impact}")
            return 0
        if args.command in ("privacy", "restore"):
            return settings_cli.handle(
                args, registry, services=services, animations=animations, on_preview=on_preview
            )
        if args.command == "services":
            if args.action == "list":
                for option in SERVICES:
                    print(f"{option.name:20} {option.effect}")
                return 0
            manager = services if services is not None else WindowsServices()
            changes, skipped = plan_services(args.ids or ["all"], manager.inventory())
            if on_preview is not None:
                on_preview(len(changes))
            print(paint(f"Preview: disable {len(changes)} optional service(s)", "title"))
            for reason in skipped:
                print(paint("[SKIP] " + reason, "warning"))
            for change in changes:
                option = next(option for option in SERVICES if option.name == change.before.name)
                print(f"  - {option.title}: {option.effect}")
            if not changes:
                print("Nothing to change.")
            elif apply_requested(args):
                apply_service_changes(changes, manager, args.log_dir)
            return 0
        if args.command == "animations":
            manager = animations if animations is not None else WindowsAnimations(registry=registry)
            state = manager.read()
            if on_preview is not None:
                on_preview(any(state.values.values()) or state.taskbar != RegistryValue(4, 0))
            print(paint("Preview: turn off Windows animations for this account", "title"))
            print("Includes window minimize/restore, taskbar, menus, tooltips, and fades.")
            print("Apps with their own animation settings may ignore Windows preferences.")
            print(f"Currently enabled: {sum(state.values.values())} Windows effect group(s).")
            if apply_requested(args):
                disable_animations(manager, args.log_dir)
                print(
                    paint(
                        "[OK] Windows animations disabled. Sign out if the taskbar still animates.",
                        "success",
                    )
                )
            return 0
        if args.command == "edge":
            manager = edge if edge is not None else WindowsEdge()
            installations = manager.inventory()
            if on_preview is not None:
                on_preview(len(installations))
            if not installations:
                print("Microsoft Edge is not installed for this machine/current account.")
                return 0
            print(paint("Preview: force uninstall Microsoft Edge", "title"))
            print("Edge windows will close; save your work. Uses the signed vendor uninstaller.")
            print(
                paint(
                    "If uninstall is blocked, force-delete only Edge's installation files.",
                    "warning",
                )
            )
            print("Forced deletion may leave an installed-app entry; updates may restore Edge.")
            print("Browser removal has no settings-backup undo. Windows may restrict removal.")
            for item in installations:
                print("  - Microsoft Edge: " + ("machine-wide" if item.system else "this account"))
            if not apply_requested(args):
                return 0
            journal = Journal(args.log_dir)
            try:
                for item in installations:
                    journal.write("started", operation="edge", installation=asdict(item))
                    try:
                        result = manager.remove(item)
                    except (BackendError, KeyboardInterrupt) as error:
                        journal.write(
                            "uncertain", operation="edge", error=str(error) or "Interrupted"
                        )
                        raise
                    journal.write(
                        "removed", operation="edge", method=result, installation=asdict(item)
                    )
                    status = (
                        "[FORCE-DELETED] Edge files"
                        if result == "force-deleted"
                        else "[REMOVED] Microsoft Edge"
                    )
                    print(paint(status, "success"))
            finally:
                journal.close()
            return 0
        if args.command == "remove" and any(
            app_id != "all"
            and app_id not in {app.id for app in CATALOG}
            and not removable_name(app_id)
            for app_id in args.apps
        ):
            raise ValueError("Choose app IDs from scan or all; wildcards are not accepted.")
        return remove_apps(args, backend if backend is not None else WindowsBackend(), on_preview)
    except (BackendError, ValueError, OSError) as error:
        print(paint(f"[ERROR] {error}", "error"), file=sys.stderr)
        print(
            "Stopped. Keep the latest backup and action log if changes already started.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt, EOFError:
        print("Cancelled. Keep the latest backup if changes already started.", file=sys.stderr)
        return 130
