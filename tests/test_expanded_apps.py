import unittest

from xnebula.core import Package, available_apps, build_plan


class ExpandedAppsTests(unittest.TestCase):
    def test_optional_media_extensions_have_clear_names_and_can_be_removed(self):
        names = {
            "Microsoft.HEVCVideoExtension": "HEVC Video Extensions",
            "Microsoft.HEIFImageExtension": "HEIF Image Extensions",
            "Microsoft.AV1VideoExtension": "AV1 Video Extension",
            "Microsoft.VP9VideoExtensions": "VP9 Video Extensions",
            "Microsoft.WebMediaExtensions": "Web Media Extensions",
            "Microsoft.WebpImageExtension": "WebP Image Extensions",
            "Microsoft.MPEG2VideoExtension": "MPEG-2 Video Extension",
            "Microsoft.RawImageExtension": "Raw Image Extension",
        }
        packages = [Package(name, name + "_1", "installed") for name in names]
        self.assertEqual({app.name: app.title for app in available_apps(packages)}, names)
        self.assertEqual({p.name for p in build_plan(["all"], packages)}, set(names))
        self.assertEqual(
            [p.name for p in build_plan(["Microsoft.HEVCVideoExtension"], packages)],
            ["Microsoft.HEVCVideoExtension"],
        )

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
