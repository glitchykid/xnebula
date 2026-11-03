"""Refuse unreviewed changes and pin recovery plans across user confirmation."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_system_actions
from test_app import FakeBackend, package
from test_settings import MemoryRegistry
from test_system_actions import MemoryServices

from xnebula.animations import ANIMATION_FLAGS, AnimationState, disable_animations
from xnebula.cli import main
from xnebula.core import Package
from xnebula.edge import EdgeInstallation
from xnebula.services import ServiceState, apply_service_changes, plan_services
from xnebula.settings import SETTINGS, RegistryValue, apply_changes, plan_settings


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.output = io.StringIO()

    def run_cli(self, args, answer, **managers):
        with (
            contextlib.redirect_stdout(self.output),
            contextlib.redirect_stderr(self.output),
            patch("builtins.input", side_effect=answer),
        ):
            return main(args, **managers)

    def test_animation_changes_during_confirmation_are_not_silently_overwritten(self):
        manager = test_system_actions.AnimationTests().manager()

        def answer(_):
            manager.state = AnimationState({flag.id: False for flag in ANIMATION_FLAGS}, None)
            return "APPLY"

        code = self.run_cli(
            ["animations", "disable", "--apply", "--log-dir", str(self.directory)],
            answer,
            animations=manager,
        )
        self.assertEqual(code, 1)
        manager.configure.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_menu_refuses_privacy_plan_changed_after_the_preview(self):
        registry = MemoryRegistry()
        registry.values[SETTINGS["location"].target] = RegistryValue(4, 0)
        answers = iter(["3", "APPLY", "0"])

        def answer(_):
            value = next(answers)
            if value == "APPLY":
                registry.values[SETTINGS["location"].target] = RegistryValue(4, 1)
            return value

        with contextlib.chdir(self.directory):
            self.assertEqual(self.run_cli(["menu"], answer, registry=registry), 0)
        self.assertEqual(registry.writes, [])
        self.assertIn("[FAILED]", self.output.getvalue())

    def test_menu_refuses_new_packages_added_between_preview_and_apply(self):
        backend = FakeBackend([package()])
        answers = iter(["1", "all", "APPLY", "0"])

        def answer(_):
            value = next(answers)
            if value == "APPLY":
                backend.packages.append(package("provisioned"))
            return value

        with contextlib.chdir(self.directory), patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(self.run_cli(["menu"], answer, backend=backend), 0)
        self.assertEqual(backend.removed, [])

    def test_direct_removal_refuses_inventory_changes_while_confirming(self):
        backend = FakeBackend([package()])

        def answer(_):
            backend.packages.append(Package("Microsoft.XboxApp", "xbox_1", "installed"))
            return "APPLY"

        code = self.run_cli(
            ["remove", "all", "--apply", "--log-dir", str(self.directory)],
            answer,
            backend=backend,
        )
        self.assertEqual(code, 1)
        self.assertEqual(backend.removed, [])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_edge_removal_refuses_changed_installations_while_confirming(self):
        manager = Mock()
        manager.inventory.return_value = [EdgeInstallation("edge.exe", "setup.exe", True)]
        manager.remove.return_value = "uninstalled"

        def answer(_):
            manager.inventory.return_value = [EdgeInstallation("edge.exe", "new-setup.exe", True)]
            return "APPLY"

        code = self.run_cli(
            ["edge", "remove", "--apply", "--log-dir", str(self.directory)], answer, edge=manager
        )
        self.assertEqual(code, 1)
        manager.remove.assert_not_called()

    def test_service_restore_applies_the_reviewed_plan_if_backup_is_replaced(self):
        manager = MemoryServices(
            [
                ServiceState("DiagTrack", "Auto", "Running"),
                ServiceState("Spooler", "Manual", "Stopped"),
            ]
        )
        changes, _ = plan_services(["all"], manager.inventory())
        with contextlib.redirect_stdout(self.output):
            backup = apply_service_changes(changes, manager, self.directory)
        document = json.loads(backup.read_text(encoding="utf-8"))
        manager.calls.clear()

        def answer(_):
            document["changes"] = [document["changes"][0]]
            backup.write_text(json.dumps(document), encoding="utf-8")
            return "APPLY"

        code = self.run_cli(
            ["restore", str(backup), "--apply", "--log-dir", str(self.directory)],
            answer,
            services=manager,
        )
        self.assertEqual(code, 0)
        self.assertEqual({change.after.name for change in manager.calls}, {"DiagTrack", "Spooler"})

    def test_animation_restore_applies_reviewed_values_if_backup_is_replaced(self):
        manager = test_system_actions.AnimationTests().manager()
        with contextlib.redirect_stdout(self.output):
            backup = disable_animations(manager, self.directory)
        document = json.loads(backup.read_text(encoding="utf-8"))

        def answer(_):
            document["before"]["values"][ANIMATION_FLAGS[0].id] = False
            backup.write_text(json.dumps(document), encoding="utf-8")
            return "APPLY"

        code = self.run_cli(
            ["restore", str(backup), "--apply", "--log-dir", str(self.directory)],
            answer,
            animations=manager,
        )
        self.assertEqual(code, 0)
        self.assertTrue(all(manager.state.values.values()))

    def test_menu_refuses_service_animation_and_edge_plans_changed_after_preview(self):
        services = MemoryServices([ServiceState("DiagTrack", "Auto", "Running")])
        animations = test_system_actions.AnimationTests().manager()
        edge = Mock()
        edge.inventory.return_value = [EdgeInstallation("edge.exe", "setup.exe", True)]

        def change_service():
            services.states["DiagTrack"] = ServiceState("DiagTrack", "Manual", "Running")

        def change_animation():
            animations.state.values[ANIMATION_FLAGS[0].id] = False

        def change_edge():
            edge.inventory.return_value = [EdgeInstallation("edge.exe", "new-setup.exe", True)]

        for choice, mutate, managers in (
            ("2", change_service, {"services": services}),
            ("4", change_animation, {"animations": animations}),
            ("5", change_edge, {"edge": edge}),
        ):
            with self.subTest(choice=choice), contextlib.chdir(self.directory):
                answers = iter(
                    [choice, "all", "APPLY", "0"] if choice == "2" else [choice, "APPLY", "0"]
                )

                def answer(_, answers=answers, mutate=mutate):
                    value = next(answers)
                    if value == "APPLY":
                        mutate()
                    return value

                self.assertEqual(self.run_cli(["menu"], answer, **managers), 0)
        self.assertEqual(services.calls, [])
        animations.configure.assert_not_called()
        edge.remove.assert_not_called()

    def test_menu_refuses_replacement_backup_plans_for_every_restore_kind(self):
        for kind in ("settings", "services", "animations"):
            with (
                self.subTest(kind=kind),
                tempfile.TemporaryDirectory() as directory,
                contextlib.chdir(directory),
                contextlib.redirect_stdout(self.output),
            ):
                logs = Path(".xnebula/logs")
                if kind == "settings":
                    manager = MemoryRegistry()
                    changes, _ = plan_settings("privacy", ["location", "camera"], manager)
                    backup = apply_changes(changes, manager, logs)
                    manager.writes.clear()
                    managers = {"registry": manager}
                elif kind == "services":
                    manager = MemoryServices(
                        [
                            ServiceState("DiagTrack", "Auto", "Running"),
                            ServiceState("Spooler", "Manual", "Stopped"),
                        ]
                    )
                    changes, _ = plan_services(["all"], manager.inventory())
                    backup = apply_service_changes(changes, manager, logs)
                    manager.calls.clear()
                    managers = {"services": manager}
                else:
                    manager = test_system_actions.AnimationTests().manager()
                    backup = disable_animations(manager, logs)
                    manager.configure.reset_mock()
                    managers = {"animations": manager}
                document = json.loads(backup.read_text(encoding="utf-8"))
                answers = iter(["6", "1", "APPLY", "0"])

                def answer(_, answers=answers, kind=kind, document=document, backup=backup):
                    value = next(answers)
                    if value == "APPLY":
                        if kind == "animations":
                            document["before"]["values"][ANIMATION_FLAGS[0].id] = False
                        else:
                            document["changes"] = [document["changes"][0]]
                        backup.write_text(json.dumps(document), encoding="utf-8")
                    return value

                self.assertEqual(self.run_cli(["menu"], answer, **managers), 0)
                if kind == "settings":
                    self.assertEqual(manager.writes, [])
                elif kind == "services":
                    self.assertEqual(manager.calls, [])
                else:
                    manager.configure.assert_not_called()

    def test_already_disabled_animations_do_not_ask_for_confirmation_or_create_logs(self):
        manager = test_system_actions.AnimationTests().manager()
        manager.state = AnimationState(
            {flag.id: False for flag in ANIMATION_FLAGS}, RegistryValue(4, 0)
        )
        code = self.run_cli(
            ["animations", "disable", "--apply", "--log-dir", str(self.directory)],
            AssertionError("No confirmation needed"),
            animations=manager,
        )
        self.assertEqual(code, 0)
        manager.configure.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])
