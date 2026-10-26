"""Data-only reusable profiles and local action reports."""

import json
from collections import Counter
from pathlib import Path

from xnebula.core import selected_apps
from xnebula.settings import SETTINGS
from xnebula.settings_cli import mutation_options

FIELDS = {
    "schema",
    "apps",
    "privacy",
    "startup",
    "background",
    "storage",
    "recall",
    "downloads_days",
    "recycle_days",
}


def validate_profile(document):
    if not isinstance(document, dict) or set(document) != FIELDS or document["schema"] != 1:
        raise ValueError("Invalid XNebula profile schema.")
    for name in ("apps", "privacy", "startup", "background"):
        values = document[name]
        if not isinstance(values, list) or any(
            not isinstance(v, str) or not v or v.startswith("-") or "\0" in v for v in values
        ):
            raise ValueError(f"Invalid profile list: {name}.")
    if document["apps"]:
        selected_apps(document["apps"])
    privacy = document["privacy"]
    if privacy != ["all"] and any(
        key not in SETTINGS or SETTINGS[key].group != "privacy" for key in privacy
    ):
        raise ValueError("Invalid privacy setting in profile.")
    if any(type(document[key]) is not bool for key in ("storage", "recall")):
        raise ValueError("Profile storage/recall flags must be booleans.")
    if any(
        type(document[key]) is not int or not 0 <= document[key] <= 365
        for key in ("downloads_days", "recycle_days")
    ):
        raise ValueError("Profile retention must be 0-365 days.")
    return document


def profile_commands(document):
    validate_profile(document)
    commands = []
    if document["privacy"]:
        commands.append(["privacy", "set", *document["privacy"]])
    if document["storage"]:
        commands.append(
            [
                "storage",
                "configure",
                "--downloads-days",
                str(document["downloads_days"]),
                "--recycle-days",
                str(document["recycle_days"]),
            ]
        )
    if document["recall"]:
        commands.append(["recall", "disable"])
    for kind in ("startup", "background"):
        if document[kind]:
            commands.append([kind, "disable", *document[kind]])
    # Background control must run before removal of any selected package.
    if document["apps"]:
        commands.append(["remove", *document["apps"]])
    return commands


def add_commands(commands):
    profile = commands.add_parser("profile", help="Save or run a reusable JSON configuration.")
    sub = profile.add_subparsers(dest="action", required=True)
    save = sub.add_parser("save", allow_abbrev=False)
    save.add_argument("path", type=Path)
    for name in ("apps", "privacy", "startup", "background"):
        save.add_argument("--" + name, nargs="*", default=[])
    for name in ("storage", "recall"):
        save.add_argument("--" + name, action="store_true")
    save.add_argument("--downloads-days", type=int, default=0)
    save.add_argument("--recycle-days", type=int, default=0)
    run = sub.add_parser("run")
    run.add_argument("path", type=Path)
    mutation_options(run)
    report = commands.add_parser("report", help="Summarize local action journals.")
    report.add_argument("--log-dir", type=Path, default=Path(".xnebula/logs"))


def handle(args, invoke):
    if args.command == "report":
        files = sorted(args.log_dir.glob("*.jsonl"))
        if not files:
            print("No action journals found.")
        for path in files:
            counts = Counter()
            print(path.name)
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                    status = event["status"]
                    if not isinstance(status, str):
                        raise ValueError
                    counts[status] += 1
                    subject = (
                        event.get("package", {}).get("name")
                        or event.get("change", {}).get("label")
                        or event.get("backup", "")
                    )
                    print(f"  {status:12} {subject}")
                except ValueError, KeyError, TypeError, AttributeError:
                    print("  Unreadable journal record (possibly interrupted write).")
            pending = (
                counts["started"] - counts["removed"] - counts["configured"] - counts["uncertain"]
            )
            print(
                f"  Verified: {counts['removed'] + counts['configured']}; "
                f"uncertain: {counts['uncertain']}; unfinished: {max(0, pending)}"
            )
        return 0
    if args.action == "save":
        document = {key: getattr(args, key) for key in FIELDS - {"schema"}}
        document["schema"] = 1
        validate_profile(document)
        with args.path.open("x", encoding="utf-8") as file:
            json.dump(document, file, indent=2)
        print(f"Saved {args.path}. Preview with 'profile run'.")
        return 0
    commands = profile_commands(json.loads(args.path.read_text(encoding="utf-8")))
    # Preflight all sections before any writes; each section scans again when applied.
    for command in commands:
        if invoke(command):
            return 1
    if args.apply and commands:
        if not args.yes and input("Type APPLY to apply this complete profile: ").strip() != "APPLY":
            print("Cancelled. No changes made.")
            return 0
        for command in commands:
            if invoke([*command, "--apply", "--yes", "--log-dir", str(args.log_dir)]):
                return 1
    return 0
