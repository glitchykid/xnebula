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


ANIMATION_TASKBAR = Target(
    "HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarAnimations"
)


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
        "Reduce diagnostics: off on supported Enterprise/Education; required only on Pro.",
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
        "privacy",
        "WindowsAI",
        "DisableAIDataAnalysis",
        1,
        "Disable Recall snapshots. Windows deletes existing snapshots; backup cannot restore them.",
    ),
}
PERMISSIONS = (
    ("camera", "LetAppsAccessCamera", "Blocks packaged apps from using the camera."),
    (
        "microphone",
        "LetAppsAccessMicrophone",
        "Blocks packaged-app microphone access; calls and recording can stop working.",
    ),
    ("contacts", "LetAppsAccessContacts", "Blocks packaged-app access to contacts."),
    ("calendar", "LetAppsAccessCalendar", "Blocks packaged-app access to calendars."),
    ("email", "LetAppsAccessEmail", "Blocks packaged-app access to email."),
    ("call-history", "LetAppsAccessCallHistory", "Blocks packaged-app access to call history."),
    ("messaging", "LetAppsAccessMessaging", "Blocks packaged-app messaging access."),
    ("tasks", "LetAppsAccessTasks", "Blocks packaged-app access to tasks."),
    (
        "account-info",
        "LetAppsAccessAccountInfo",
        "Blocks packaged-app access to account information.",
    ),
    (
        "app-diagnostics",
        "LetAppsGetDiagnosticInfo",
        "Blocks apps from reading other apps' diagnostic information.",
    ),
    (
        "background-apps",
        "LetAppsRunInBackground",
        "Stops packaged-app background activity; notifications and syncing can stop.",
    ),
)
SETTINGS.update(
    {key: setting("privacy", "AppPrivacy", name, 2, effect) for key, name, effect in PERMISSIONS}
)
SETTINGS["online-speech"] = Setting(
    "privacy",
    Target(
        "HKLM", r"Software\Policies\Microsoft\InputPersonalization", "AllowInputPersonalization"
    ),
    0,
    "Disables online speech recognition.",
)
SETTINGS["clipboard-sync"] = setting(
    "privacy",
    "System",
    "AllowCrossDeviceClipboard",
    0,
    "Disables clipboard synchronization between devices.",
)
PERMISSION_EXCEPTIONS = {
    Target("HKLM", POLICY + r"\AppPrivacy", name + suffix)
    for _, name, _ in PERMISSIONS
    for suffix in ("_ForceAllowTheseApps", "_UserInControlOfTheseApps")
}

# Retain validation of old backups without exposing removed features in the app.
LEGACY_STORAGE_TARGETS = {
    Target("HKLM", POLICY + r"\StorageSense", name)
    for name in (
        "AllowStorageSenseGlobal",
        "AllowStorageSenseTemporaryFilesCleanup",
        "ConfigStorageSenseGlobalCadence",
        "ConfigStorageSenseDownloadsCleanupThreshold",
        "ConfigStorageSenseRecycleBinCleanupThreshold",
        "ConfigStorageSenseCloudContentDehydrationThreshold",
    )
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


def plan_settings(group, ids, registry):
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
        if key == "recall-snapshots" and not registry.recall_available:
            skipped.append(f"{key}: Recall feature or required Windows update is unavailable")
            continue
        before = registry.read(option.target)
        if before is not None and before.type != 4:
            raise ValueError(f"{key} has an unexpected registry type; refusing to replace it.")
        if key == "diagnostics" and before == RegistryValue(4, 0):
            continue
        desired = 0 if key == "diagnostics" and enterprise else option.desired
        after = RegistryValue(4, desired)
        if before != after:
            changes.append(Change(option.target, before, after, key))
        if any(permission_id == key for permission_id, _, _ in PERMISSIONS):
            for suffix in ("_ForceAllowTheseApps", "_UserInControlOfTheseApps"):
                target = Target(option.target.hive, option.target.key, option.target.name + suffix)
                exceptions = registry.read(target)
                if exceptions is not None:
                    if exceptions.type != 7:
                        raise ValueError(
                            f"Unexpected {key} exception-list type; no changes started."
                        )
                    if exceptions.data:
                        changes.append(
                            Change(target, exceptions, RegistryValue(7, []), key + " exceptions")
                        )
    return changes, skipped


def validate_target(target):
    known = (
        {option.target for option in SETTINGS.values()}
        | set(BACKGROUND.values())
        | {ANIMATION_TASKBAR}
        | LEGACY_STORAGE_TARGETS
        | PERMISSION_EXCEPTIONS
    )
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
