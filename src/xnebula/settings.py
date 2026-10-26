"""Explicit registry plans, backups, conflict detection, and restoration."""

import json
import os
from dataclasses import asdict, dataclass
from uuid import uuid4

from xnebula.journal import Journal

POLICY = r"Software\Policies\Microsoft\Windows"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_KEYS = {
    "user": ("HKCU", RUN),
    "machine": ("HKLM", RUN),
    "machine32": ("HKLM", r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
}


@dataclass(frozen=True)
class Target:
    hive: str
    key: str
    name: str


@dataclass(frozen=True)
class RegistryValue:
    type: int
    data: int | str | list[str]


@dataclass(frozen=True)
class Setting:
    group: str
    target: Target
    desired: int
    effect: str
    enterprise_only: bool = False


def setting(group, branch, name, value, effect, *, user=False, enterprise=False):
    return Setting(
        group,
        Target("HKCU" if user else "HKLM", POLICY + "\\" + branch, name),
        value,
        effect,
        enterprise,
    )


SETTINGS = {
    "advertising": setting(
        "privacy",
        "AdvertisingInfo",
        "DisabledByGroupPolicy",
        1,
        "Turn off advertising ID for all accounts.",
    ),
    "diagnostics": setting(
        "privacy",
        "DataCollection",
        "AllowTelemetry",
        1,
        "Limit Windows diagnostics to required data; preserve an existing zero.",
    ),
    "tailored": setting(
        "privacy",
        "CloudContent",
        "DisableTailoredExperiencesWithDiagnosticData",
        1,
        "Disable diagnostic-based tailored experiences for the current account.",
        user=True,
    ),
    "suggestions": setting(
        "privacy",
        "CloudContent",
        "DisableWindowsSpotlightOnSettings",
        1,
        "Disable Settings suggestions for the current account (Enterprise/Education).",
        user=True,
        enterprise=True,
    ),
    "consumer-content": setting(
        "privacy",
        "CloudContent",
        "DisableWindowsConsumerFeatures",
        1,
        "Disable suggested consumer experiences system-wide (Enterprise/Education).",
        enterprise=True,
    ),
    "activity-feed": setting(
        "privacy", "System", "EnableActivityFeed", 0, "Disable the activity feed for all accounts."
    ),
    "activity-publishing": setting(
        "privacy",
        "System",
        "PublishUserActivities",
        0,
        "Stop publishing user activities; does not erase existing history.",
    ),
    "activity-upload": setting(
        "privacy",
        "System",
        "UploadUserActivities",
        0,
        "Stop uploading user activities; does not erase existing history.",
    ),
    "location": setting(
        "privacy",
        "LocationAndSensors",
        "DisableLocation",
        1,
        "Disable Windows location for all accounts; location-dependent features stop working.",
    ),
    "recall-snapshots": setting(
        "recall",
        "WindowsAI",
        "DisableAIDataAnalysis",
        1,
        "Disable Recall snapshots. Windows deletes existing snapshots; backup cannot restore them.",
    ),
    "storage-downloads": setting(
        "storage",
        "StorageSense",
        "ConfigStorageSenseDownloadsCleanupThreshold",
        0,
        "Downloads cleanup: 0 keeps files; positive values set unused days before deletion.",
    ),
    "storage-recycle": setting(
        "storage",
        "StorageSense",
        "ConfigStorageSenseRecycleBinCleanupThreshold",
        0,
        "Recycle Bin cleanup: 0 keeps items; a positive value permanently deletes older items.",
    ),
    "storage-cloud": setting(
        "storage",
        "StorageSense",
        "ConfigStorageSenseCloudContentDehydrationThreshold",
        0,
        "Keep cloud-backed files available locally.",
    ),
    "storage-temporary": setting(
        "storage",
        "StorageSense",
        "AllowStorageSenseTemporaryFilesCleanup",
        1,
        "Allow Windows to clean unused temporary files.",
    ),
    "storage-cadence": setting(
        "storage",
        "StorageSense",
        "ConfigStorageSenseGlobalCadence",
        0,
        "Run Storage Sense when disk space is low.",
    ),
    "storage-enable": setting(
        "storage",
        "StorageSense",
        "AllowStorageSenseGlobal",
        1,
        "Enable Storage Sense; scheduled cleanup is not an immediate disk cleanup.",
    ),
}
BACKGROUND = {
    name: Target("HKLM", POLICY + r"\AppPrivacy", "LetAppsRunInBackground" + suffix)
    for name, suffix in (
        ("default", ""),
        ("deny", "_ForceDenyTheseApps"),
        ("allow", "_ForceAllowTheseApps"),
        ("control", "_UserInControlOfTheseApps"),
    )
}


@dataclass(frozen=True)
class Change:
    target: Target
    before: RegistryValue | None
    after: RegistryValue | None
    label: str


def supports_policies(edition):
    return edition.startswith(("Professional", "Enterprise", "Education", "IoTEnterprise"))


def plan_settings(group, ids, registry, *, downloads_days=0, recycle_days=0):
    if any(
        type(days) is not int or not 0 <= days <= 365 for days in (downloads_days, recycle_days)
    ):
        raise ValueError("Retention must be between 0 (never delete) and 365 days.")
    available = {key: value for key, value in SETTINGS.items() if value.group == group}
    if ids == ["all"]:
        ids = list(available)
    if not ids or any(key not in available for key in ids):
        raise ValueError(f"Choose IDs from '{group} list', or 'all' on its own.")
    changes, skipped = [], []
    for key in dict.fromkeys(ids):
        option = available[key]
        enterprise = registry.edition.startswith(("Enterprise", "Education", "IoTEnterprise"))
        if not supports_policies(registry.edition) or (option.enterprise_only and not enterprise):
            skipped.append(f"{key}: unsupported edition {registry.edition}")
            continue
        if group == "recall" and not registry.recall_available:
            skipped.append(f"{key}: Recall feature or required Windows update is unavailable")
            continue
        before = registry.read(option.target)
        if before is not None and before.type != 4:
            raise ValueError(f"{key} has an unexpected registry type; refusing to replace it.")
        if key == "diagnostics" and before == RegistryValue(4, 0):
            continue
        desired = {"storage-downloads": downloads_days, "storage-recycle": recycle_days}.get(
            key, option.desired
        )
        after = RegistryValue(4, desired)
        if before != after:
            changes.append(Change(option.target, before, after, key))
    return changes, skipped


def plan_startup(ids, registry):
    entries = registry.startup()
    if not ids or any(key not in entries for key in ids):
        raise ValueError("Choose exact scoped IDs from 'startup list'.")
    changes = []
    for key in dict.fromkeys(ids):
        before = registry.read(entries[key])
        if before is None or before.type not in (1, 2):
            raise ValueError(f"Startup entry {key} changed or has an unsupported value type.")
        changes.append(Change(entries[key], before, None, key))
    return changes


def plan_background(families, registry):
    if not supports_policies(registry.edition):
        raise ValueError(f"Background policies are unsupported on {registry.edition}.")
    available = registry.background_apps()
    if not families or any(family not in available for family in families):
        raise ValueError("Choose exact package family names from 'background list'.")
    changes = []
    for name, target in BACKGROUND.items():
        before = registry.read(target)
        if name == "default":
            if before is not None and before.type != 4:
                raise ValueError("Unexpected background policy type.")
            after = before or RegistryValue(4, 0)
        else:
            if before is not None and before.type != 7:
                raise ValueError("Unexpected background app list type.")
            values = before.data if before else []
            selected = {family.casefold() for family in families}
            values = [value for value in values if value.casefold() not in selected]
            after = (
                RegistryValue(7, sorted(set(values + families)))
                if name == "deny"
                else (RegistryValue(7, values) if before else None)
            )
        if before != after:
            changes.append(Change(target, before, after, f"background-{name}"))
    return changes


def validate_target(target):
    known = {option.target for option in SETTINGS.values()} | set(BACKGROUND.values())
    if target in known:
        return
    if (
        (target.hive, target.key) in STARTUP_KEYS.values()
        and target.name
        and "\0" not in target.name
    ):
        return
    raise ValueError("Backup contains a registry target outside XNebula's supported settings.")


def decode_value(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"type", "data"}:
        raise ValueError("Invalid registry value in backup.")
    kind, data = value["type"], value["data"]
    valid = type(kind) is int and (
        (kind == 4 and type(data) is int and 0 <= data <= 0xFFFFFFFF)
        or (kind in (1, 2) and isinstance(data, str) and "\0" not in data)
        or (
            kind == 7
            and isinstance(data, list)
            and all(isinstance(v, str) and v and "\0" not in v for v in data)
        )
    )
    if not valid:
        raise ValueError("Unsupported registry value in backup.")
    return RegistryValue(kind, data)


def apply_changes(changes, registry, directory):
    # Validate the complete snapshot before creating backups or performing writes.
    for change in changes:
        validate_target(change.target)
        if registry.read(change.target) != change.before:
            raise ValueError(f"{change.label} changed since preview; preview again.")
    directory.mkdir(parents=True, exist_ok=True)
    backup = directory / f"settings-{uuid4().hex}.json"
    document = {"schema": 1, "identity": registry.identity, "changes": [asdict(c) for c in changes]}
    with backup.open("x", encoding="utf-8") as file:
        json.dump(document, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    print(f"Backup: {backup.resolve()}")
    journal = Journal(directory)
    try:
        journal.write("planned", backup=str(backup.resolve()), changes=[asdict(c) for c in changes])
        for change in changes:
            if registry.read(change.target) != change.before:
                raise ValueError(f"{change.label} changed during apply; stopped.")
            journal.write("started", change=asdict(change))
            try:
                registry.write(change.target, change.after)
                if registry.read(change.target) != change.after:
                    raise OSError(f"Could not verify {change.label}.")
            except (OSError, KeyboardInterrupt) as error:
                journal.write("uncertain", change=asdict(change), error=str(error) or "Interrupted")
                raise
            journal.write("configured", change=asdict(change))
    finally:
        journal.close()
    return backup


def restore_plan(path, registry):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["schema"] != 1 or document["identity"] != registry.identity:
            raise ValueError("Backup is for a different machine/account or schema.")
        if not isinstance(document["changes"], list):
            raise ValueError("Invalid backup changes.")
        changes, seen = [], set()
        for row in reversed(document["changes"]):
            target = Target(**row["target"])
            validate_target(target)
            if target in seen or not isinstance(row["label"], str):
                raise ValueError("Duplicate target or invalid label in backup.")
            seen.add(target)
            before, after = decode_value(row["before"]), decode_value(row["after"])
            current = registry.read(target)
            if current == before:
                continue
            if current != after:
                raise ValueError(f"Restore conflict: {row['label']} changed after this backup.")
            changes.append(Change(target, current, before, "restore:" + row["label"]))
        return changes
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid XNebula backup.") from error
