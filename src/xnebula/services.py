"""Disable optional services through Windows service management, with restoration."""

import base64
import json
from dataclasses import asdict, dataclass

from xnebula.console import paint
from xnebula.journal import Journal
from xnebula.recovery import read_snapshot, save_snapshot
from xnebula.windows import BackendError, WindowsBackend


@dataclass(frozen=True)
class ServiceOption:
    name: str
    title: str
    effect: str


SERVICES = (
    ServiceOption(
        "DiagTrack", "Connected User Experiences", "Stops diagnostic telemetry service activity."
    ),
    ServiceOption(
        "dmwappushservice",
        "WAP push routing",
        "Disables WAP push message routing; may affect managed devices.",
    ),
    ServiceOption("WerSvc", "Windows Error Reporting", "Stops automatic Windows error reports."),
    ServiceOption("RemoteRegistry", "Remote Registry", "Prevents remote registry administration."),
    ServiceOption("RetailDemo", "Retail demo", "Disables retail demonstration mode."),
    ServiceOption("MapsBroker", "Downloaded maps", "Stops downloaded-map updates and access."),
    ServiceOption("lfsvc", "Geolocation", "Stops Windows location services."),
    ServiceOption("XblAuthManager", "Xbox authentication", "Xbox sign-in can stop working."),
    ServiceOption(
        "XblGameSave", "Xbox game saves", "Xbox cloud-save synchronization can stop working."
    ),
    ServiceOption("XboxGipSvc", "Xbox accessories", "Xbox accessory support can stop working."),
    ServiceOption(
        "XboxNetApiSvc", "Xbox networking", "Xbox multiplayer networking can stop working."
    ),
    ServiceOption("WMPNetworkSvc", "Media sharing", "Stops Windows Media Player network sharing."),
    ServiceOption("Fax", "Fax", "Disables fax sending and receiving."),
    ServiceOption(
        "WSearch", "Search indexing", "Stops background indexing; searches may become slower."
    ),
    ServiceOption("Spooler", "Printing", "Disables printers and Microsoft Print to PDF."),
)
NAMES = {service.name for service in SERVICES}


@dataclass(frozen=True)
class ServiceState:
    name: str
    start_mode: str
    status: str
    delayed: bool = False
    dependents: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceChange:
    before: ServiceState
    after: ServiceState


def validate_state(state):
    if (
        state.name not in NAMES
        or state.start_mode not in ("Auto", "Manual", "Disabled")
        or state.status not in ("Running", "Stopped")
        or type(state.delayed) is not bool
    ):
        raise ValueError(
            "Unsupported service or unstable service state. Try again after Windows settles."
        )
    if any(not isinstance(name, str) or not name for name in state.dependents):
        raise ValueError("Invalid service dependencies.")


def same_configuration(left, right):
    return (left.name, left.start_mode, left.status, left.delayed) == (
        right.name,
        right.start_mode,
        right.status,
        right.delayed,
    )


def plan_services(ids, states):
    if not ids or (ids != ["all"] and any(name not in NAMES for name in ids)):
        raise ValueError("Choose optional service names from services list, or all.")
    selected = NAMES if ids == ["all"] else set(ids)
    current = {state.name: state for state in states if state.name in selected}
    for state in current.values():
        validate_state(state)
    # A running dependent outside this plan blocks disabling its parent.
    blocked = {
        name
        for name, state in current.items()
        if any(dep not in current for dep in state.dependents)
    }
    while True:
        expanded = blocked | {
            name
            for name, state in current.items()
            if any(dep in blocked for dep in state.dependents)
        }
        if expanded == blocked:
            break
        blocked = expanded
    changes, visiting, visited = [], set(), set()

    def visit(name):
        if name in blocked or name in visited:
            return
        if name in visiting:
            raise ValueError("Unexpected circular service dependency; no changes started.")
        visiting.add(name)
        state = current[name]
        for dependent in state.dependents:
            visit(dependent)
        visiting.remove(name)
        visited.add(name)
        if state.start_mode != "Disabled" or state.status != "Stopped":
            changes.append(ServiceChange(state, ServiceState(name, "Disabled", "Stopped")))

    for option in SERVICES:
        if option.name in current:
            visit(option.name)
    skipped = [f"{name}: a running dependent requires this service" for name in sorted(blocked)]
    return changes, skipped


def apply_service_changes(changes, manager, directory):
    current = {state.name: state for state in manager.inventory()}
    for change in changes:
        validate_state(change.before)
        validate_state(change.after)
        if (
            change.before.name != change.after.name
            or change.before.name not in current
            or not same_configuration(current[change.before.name], change.before)
        ):
            raise ValueError("Service configuration changed since preview; preview again.")
    path = save_snapshot(
        "services", manager.identity, {"changes": [asdict(change) for change in changes]}, directory
    )
    journal = Journal(directory)
    try:
        journal.write("planned", backup=str(path.resolve()))
        for change in changes:
            journal.write("started", service=change.before.name)
            try:
                manager.configure(change)
                updated = {state.name: state for state in manager.inventory([change.after.name])}
                if change.after.name not in updated or not same_configuration(
                    updated[change.after.name], change.after
                ):
                    raise BackendError(f"Windows did not confirm {change.after.name}.")
            except (OSError, BackendError, KeyboardInterrupt) as error:
                journal.write(
                    "uncertain", service=change.before.name, error=str(error) or "Interrupted"
                )
                raise
            journal.write("configured", service=change.after.name)
            print(
                paint(
                    f"[OK] {change.after.name}: {change.after.start_mode}, {change.after.status}",
                    "success",
                )
            )
    finally:
        journal.close()
    return path


def restore_services(path, manager, directory, *, apply=True):
    document = read_snapshot(path, "services", manager.identity)
    current = {state.name: state for state in manager.inventory()}
    changes, seen = [], set()
    try:
        if not isinstance(document["changes"], list):
            raise ValueError("Invalid service backup.")
        for row in reversed(document["changes"]):
            before = ServiceState(
                **{**row["before"], "dependents": tuple(row["before"].get("dependents", []))}
            )
            after = ServiceState(
                **{**row["after"], "dependents": tuple(row["after"].get("dependents", []))}
            )
            validate_state(before)
            validate_state(after)
            if before.name in seen or before.name != after.name or before.name not in current:
                raise ValueError("Invalid or missing service in backup.")
            seen.add(before.name)
            state = current[before.name]
            if same_configuration(state, before):
                continue
            # A failed stop can leave the old running state with the new startup mode.
            if (
                state.start_mode not in (before.start_mode, after.start_mode)
                or state.status not in (before.status, after.status)
                or state.delayed not in (before.delayed, after.delayed)
            ):
                raise ValueError(f"Restore conflict: {before.name} changed after the backup.")
            changes.append(ServiceChange(state, before))
    except (TypeError, KeyError, AttributeError) as error:
        raise ValueError("Invalid service backup.") from error
    for change in changes:
        print(f"Restore {change.after.name}: {change.after.start_mode}, {change.after.status}")
    if apply and changes:
        apply_service_changes(changes, manager, directory)
    return changes


def payload(value):
    encoded = base64.b64encode(json.dumps(value).encode()).decode()
    return (
        "$target = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
        + encoded
        + "')) | ConvertFrom-Json\n"
    )


class WindowsServices:
    def __init__(self, *, bridge=None, identity=None):
        self.bridge = bridge if bridge is not None else WindowsBackend()
        if identity is None:
            from xnebula.registry import WindowsRegistry

            identity = WindowsRegistry().identity
        self.identity = identity

    def inventory(self, names=None):
        names = sorted(NAMES) if names is None else list(names)
        if any(name not in NAMES for name in names):
            raise ValueError("Unsupported service inventory request.")
        script = (
            payload(names)
            + r"""
$rows = @(foreach ($name in $target) {
    $cim = @(Get-CimInstance Win32_Service -Filter ("Name='" + $name + "'") -ErrorAction Stop)
    if ($cim.Count -eq 0) { continue }
    $service = Get-Service -Name $name -ErrorAction Stop
    [PSCustomObject]@{name=$name; start_mode=$cim[0].StartMode; status=[string]$service.Status
        delayed=[bool]($cim[0].StartMode -eq 'Auto' -and $cim[0].DelayedAutoStart)
        dependents=@($service.DependentServices | Where-Object Status -ne 'Stopped' |
            ForEach-Object { $_.Name })}
})
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""
        )
        try:
            rows = json.loads(self.bridge._run(script))
            if not isinstance(rows, list):
                raise ValueError
            states = [
                ServiceState(**{**row, "dependents": tuple(row["dependents"])}) for row in rows
            ]
            if len({state.name for state in states}) != len(states):
                raise ValueError
            for state in states:
                validate_state(state)
            return states
        except (ValueError, TypeError, KeyError) as error:
            raise BackendError("Windows returned an invalid optional-service inventory.") from error

    def configure(self, change):
        validate_state(change.before)
        validate_state(change.after)
        if change.before.name != change.after.name:
            raise ValueError("Service identity mismatch.")
        mode = {
            "Auto": "delayed-auto" if change.after.delayed else "auto",
            "Manual": "demand",
            "Disabled": "disabled",
        }[change.after.start_mode]
        script = (
            payload(
                {
                    "name": change.before.name,
                    "before": asdict(change.before),
                    "after": asdict(change.after),
                    "mode": mode,
                }
            )
            + r"""
$service = Get-Service -Name $target.name -ErrorAction Stop
$cim = Get-CimInstance Win32_Service -Filter ("Name='" + $target.name + "'") -ErrorAction Stop
$delayed = [bool]($cim.StartMode -eq 'Auto' -and $cim.DelayedAutoStart)
if ($cim.StartMode -ne $target.before.start_mode -or
    [string]$service.Status -ne $target.before.status -or
    $delayed -ne $target.before.delayed) { throw 'Service changed. Preview again.' }
if ($target.after.status -eq 'Stopped') {
    $active = @($service.DependentServices | Where-Object Status -ne 'Stopped')
    if ($active.Count -gt 0) {
        throw 'A running dependent requires this service. No forced stop attempted.'
    }
}
$mode = $target.mode
if ($target.after.start_mode -eq 'Disabled' -and $target.after.status -eq 'Running') {
    $mode = 'demand'
}
& ($env:SystemRoot + '\System32\sc.exe') config $target.name start= $mode | Out-Null
if ($LASTEXITCODE -ne 0) { throw ('Windows rejected startup configuration for ' + $target.name) }
if ($target.after.status -eq 'Stopped') {
    if ($service.Status -ne 'Stopped') { Stop-Service -Name $target.name -ErrorAction Stop }
    (Get-Service -Name $target.name).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
} else {
    if ($service.Status -ne 'Running') { Start-Service -Name $target.name -ErrorAction Stop }
    (Get-Service -Name $target.name).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    if ($target.after.start_mode -eq 'Disabled') {
        & ($env:SystemRoot + '\System32\sc.exe') config $target.name start= disabled | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not restore disabled-but-running startup state.' }
    }
}
'ok'
"""
        )
        if self.bridge._run(script) != "ok":
            raise BackendError("Windows did not confirm the service operation.")
