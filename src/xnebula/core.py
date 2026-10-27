"""Allowlisted apps and deterministic removal planning."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class App:
    id: str
    title: str
    name: str
    impact: str


CATALOG = (
    App("news", "Microsoft News", "Microsoft.BingNews", "Removes the News app."),
    App("weather", "MSN Weather", "Microsoft.BingWeather", "Removes the Weather app."),
    App(
        "solitaire",
        "Solitaire Collection",
        "Microsoft.MicrosoftSolitaireCollection",
        "Removes Solitaire games.",
    ),
    App("clipchamp", "Clipchamp", "Clipchamp.Clipchamp", "Removes the Clipchamp video editor."),
    App(
        "feedback",
        "Feedback Hub",
        "Microsoft.WindowsFeedbackHub",
        "Removes the Feedback Hub reporting app.",
    ),
    App("gethelp", "Get Help", "Microsoft.GetHelp", "Removes the Get Help support app."),
    App("tips", "Tips", "Microsoft.Getstarted", "Removes Windows tips and tutorials."),
    App(
        "maps",
        "Windows Maps",
        "Microsoft.WindowsMaps",
        "Removes the Maps app and its offline map access.",
    ),
)


@dataclass(frozen=True)
class Package:
    name: str
    full_name: str
    kind: str
    protected: bool = False


PROTECTED_APPS = (
    "Microsoft.SecHealthUI",
    "Microsoft.WindowsTerminal",
    "Microsoft.WindowsTerminalPreview",
    "Microsoft.AAD.BrokerPlugin",
    "Microsoft.AccountsControl",
    "Microsoft.AsyncTextService",
    "Microsoft.BioEnrollment",
    "Microsoft.CredDialogHost",
    "Microsoft.LockApp",
    "Microsoft.MicrosoftEdge",
    "Microsoft.Win32WebViewHost",
    "Microsoft.Windows.CloudExperienceHost",
    "Microsoft.Windows.ContentDeliveryManager",
    "Microsoft.Windows.Search",
    "Microsoft.Windows.ShellExperienceHost",
    "Microsoft.Windows.StartMenuExperienceHost",
    "Microsoft.WindowsAppRuntime",
    "Microsoft.VCLibs",
    "Microsoft.NET.Native",
    "Microsoft.UI.Xaml",
    "MicrosoftWindows.Client.CBS",
    "MicrosoftWindows.Client.Core",
    "MicrosoftWindows.Client.FileExp",
    "MicrosoftWindows.Client.OOBE",
    "MicrosoftWindows.Client.Photon",
    "MicrosoftWindows.Client.PPI",
)


def removable_name(name):
    if not isinstance(name, str) or any(
        name.casefold() == prefix.casefold() or name.casefold().startswith(prefix.casefold() + ".")
        for prefix in PROTECTED_APPS
    ):
        return False
    return name in ("Clipchamp.Clipchamp", "MSTeams", "MicrosoftTeams") or bool(
        re.fullmatch(r"(?:Microsoft|MicrosoftCorporationII|MicrosoftWindows)\.[A-Za-z0-9.-]+", name)
    )


def available_apps(packages):
    known = {app.name: app for app in CATALOG}
    titles = {
        "Microsoft.Windows.Photos": "Photos",
        "Microsoft.WindowsStore": "Microsoft Store",
        "Microsoft.StorePurchaseApp": "Store purchases",
        "Microsoft.DesktopAppInstaller": "App Installer / winget",
        "Microsoft.GamingApp": "Xbox app",
        "Microsoft.XboxGamingOverlay": "Xbox Game Bar",
        "Microsoft.YourPhone": "Phone Link",
        "Microsoft.WindowsCamera": "Camera",
        "Microsoft.WindowsSoundRecorder": "Sound Recorder",
        "Microsoft.WindowsCalculator": "Calculator",
        "Microsoft.WindowsNotepad": "Notepad",
        "Microsoft.Paint": "Paint",
        "Microsoft.OutlookForWindows": "Outlook",
        "Microsoft.MicrosoftOfficeHub": "Microsoft 365 hub",
        "Microsoft.Copilot": "Copilot",
        "MSTeams": "Microsoft Teams",
        "Microsoft.MicrosoftStickyNotes": "Sticky Notes",
        "Microsoft.ZuneMusic": "Media Player",
        "Microsoft.ZuneVideo": "Movies & TV",
        "MicrosoftWindows.Client.WebExperience": "Widgets",
    }
    apps = {}
    protected = {item.name.casefold() for item in packages if item.protected}
    for item in packages:
        if not removable_name(item.name) or item.name.casefold() in protected:
            continue
        app = known.get(item.name)
        if app is None:
            title = titles.get(item.name, item.name.replace("Microsoft.", "").replace(".", " "))
            app = App(
                item.name, title, item.name, f"Removes {title} for existing and new accounts."
            )
        apps[item.name.casefold()] = app
    return sorted(apps.values(), key=lambda app: app.title.casefold())


def selected_apps(ids: list[str], packages=None) -> list[App]:
    known = {app.id: app for app in CATALOG}
    if packages is not None:
        detected = available_apps(packages)
        known.update({app.id: app for app in detected})
        if ids == ["all"]:
            return detected
    if not ids or any(app_id not in known for app_id in ids):
        raise ValueError("Choose apps from the numbered list, exact IDs from scan, or all.")
    return [known[app_id] for app_id in dict.fromkeys(ids)]


def build_plan(ids: list[str], packages: list[Package]) -> list[Package]:
    names = {app.name.casefold() for app in selected_apps(ids, packages)}
    result = []
    seen = set()
    for item in packages:
        if item.name.casefold() not in names:
            continue
        if item.protected:
            raise ValueError(f"Windows marks {item.name} as protected; no changes were started.")
        key = (item.kind, item.full_name.casefold())
        if key not in seen:
            seen.add(key)
            result.append(item)
    # Existing accounts first, then future accounts; stop if an installed removal fails.
    return sorted(result, key=lambda item: (item.kind, item.full_name))
