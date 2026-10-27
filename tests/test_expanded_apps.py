import unittest

from xnebula.core import Package, available_apps, build_plan


class ExpandedAppsTests(unittest.TestCase):
    def test_all_discovers_windows_apps_beyond_the_old_catalog(self):
        packages = [
            Package("Microsoft.Windows.Photos", "photos_1", "installed"),
            Package("Microsoft.WindowsStore", "store_1", "provisioned"),
            Package("Microsoft.GamingApp", "xbox_1", "installed"),
        ]
        self.assertEqual(
            {item.name for item in build_plan(["all"], packages)}, {item.name for item in packages}
        )
        self.assertEqual(len(available_apps(packages)), 3)

    def test_all_excludes_third_party_protected_runtime_and_security_components(self):
        packages = [
            Package("Microsoft.Windows.Photos", "photos", "installed"),
            Package("Vendor.Program", "thirdparty", "installed"),
            Package("Microsoft.SecHealthUI", "security", "installed"),
            Package("Microsoft.VCLibs.140.00", "runtime", "installed"),
            Package("Microsoft.WindowsTerminal", "terminal", "installed"),
            Package("Microsoft.ShellExperienceHost", "shell", "installed", True),
        ]
        self.assertEqual(
            [item.name for item in build_plan(["all"], packages)], ["Microsoft.Windows.Photos"]
        )

    def test_dynamic_app_names_can_be_selected_individually(self):
        packages = [
            Package("Microsoft.Windows.Photos", "photos", "installed"),
            Package("Microsoft.WindowsStore", "store", "installed"),
        ]
        apps = available_apps(packages)
        self.assertEqual(len(build_plan([apps[0].id], packages)), 1)
        self.assertEqual(build_plan(["all"], []), [])
