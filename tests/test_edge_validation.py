import json
import unittest
from unittest.mock import Mock

from xnebula.edge import EdgeInstallation, WindowsEdge
from xnebula.windows import BackendError


class EdgeValidationTests(unittest.TestCase):
    def test_malformed_removal_targets_never_reach_the_native_bridge(self):
        for item in (
            None,
            EdgeInstallation("edge.exe", "", 1),
            EdgeInstallation("edge.exe", "", "false"),
            EdgeInstallation("edge.exe", None, True),
            EdgeInstallation("edge.exe", "   ", True),
            EdgeInstallation("   ", "", True),
            EdgeInstallation([], "", True),
        ):
            with self.subTest(item=item):
                bridge = Mock()
                with self.assertRaises(BackendError):
                    WindowsEdge(bridge=bridge).remove(item)
                bridge._run.assert_not_called()

    def test_blank_inventory_paths_are_reported_as_invalid_data(self):
        for executable, installer in ((" ", ""), ("edge.exe", " ")):
            with self.subTest(executable=executable, installer=installer):
                bridge = Mock()
                bridge._run.return_value = json.dumps(
                    [{"executable": executable, "installer": installer, "system": True}]
                )
                with self.assertRaisesRegex(BackendError, "invalid Microsoft Edge inventory"):
                    WindowsEdge(bridge=bridge).inventory()
