"""Allowlisted apps and deterministic removal planning."""

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


def selected_apps(ids: list[str]) -> list[App]:
    known = {app.id: app for app in CATALOG}
    if not ids or any(app_id not in known for app_id in ids):
        raise ValueError("Choose exact app IDs from 'xnebula catalog'; wildcards are not accepted.")
    return [known[app_id] for app_id in dict.fromkeys(ids)]


def build_plan(ids: list[str], packages: list[Package]) -> list[Package]:
    names = {app.name.casefold() for app in selected_apps(ids)}
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
