"""Disable Windows-managed animations using documented user-preference APIs."""

import ctypes
from dataclasses import asdict, dataclass

from xnebula.journal import Journal
from xnebula.recovery import read_snapshot, save_snapshot
from xnebula.settings import ANIMATION_TASKBAR, RegistryValue, decode_value


@dataclass(frozen=True)
class AnimationFlag:
    id: str
    get_action: int
    set_action: int


ANIMATION_FLAGS = (
    AnimationFlag("ui-effects", 0x103E, 0x103F),
    AnimationFlag("client-area", 0x1042, 0x1043),
    AnimationFlag("menus", 0x1002, 0x1003),
    AnimationFlag("combo-boxes", 0x1004, 0x1005),
    AnimationFlag("smooth-scrolling", 0x1006, 0x1007),
    AnimationFlag("menu-fades", 0x1012, 0x1013),
    AnimationFlag("selection-fades", 0x1014, 0x1015),
    AnimationFlag("tooltips", 0x1016, 0x1017),
    AnimationFlag("tooltip-fades", 0x1018, 0x1019),
    AnimationFlag("minimize-restore", 0x0048, 0x0049),
)


class AnimationInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("iMinAnimate", ctypes.c_int)]


@dataclass(frozen=True)
class AnimationState:
    values: dict[str, bool]
    taskbar: RegistryValue | None


def decode_state(row):
    try:
        if (
            set(row) != {"values", "taskbar"}
            or set(row["values"]) != {flag.id for flag in ANIMATION_FLAGS}
            or any(type(value) is not bool for value in row["values"].values())
        ):
            raise ValueError("Invalid animation settings in backup.")
        taskbar = decode_value(row["taskbar"])
        if taskbar is not None and taskbar.type != 4:
            raise ValueError("Invalid taskbar animation setting.")
        return AnimationState(dict(row["values"]), taskbar)
    except (TypeError, KeyError, AttributeError) as error:
        raise ValueError("Invalid animation backup.") from error


def apply_animation_state(manager, before, after, directory):
    if manager.read() != before:
        raise ValueError("Animation settings changed since preview; preview again.")
    path = save_snapshot(
        "animations",
        manager.identity,
        {"before": asdict(before), "after": asdict(after)},
        directory,
    )
    journal = Journal(directory)
    try:
        journal.write("started", backup=str(path.resolve()), operation="animations")
        try:
            manager.configure(before, after)
            if manager.read() != after:
                raise OSError("Windows did not confirm every animation setting. Check the backup.")
        except (OSError, KeyboardInterrupt) as error:
            journal.write("uncertain", operation="animations", error=str(error) or "Interrupted")
            raise
        journal.write("configured", operation="animations")
    finally:
        journal.close()
    return path


def disable_animations(manager, directory):
    before = manager.read()
    after = AnimationState({flag.id: False for flag in ANIMATION_FLAGS}, RegistryValue(4, 0))
    if before == after:
        print("[OK] Windows animations are already disabled.")
        return None
    return apply_animation_state(manager, before, after, directory)


def restore_animations(path, manager, directory, *, apply=True):
    document = read_snapshot(path, "animations", manager.identity)
    try:
        before, after = decode_state(document["before"]), decode_state(document["after"])
    except KeyError as error:
        raise ValueError("Invalid animation backup.") from error
    current = manager.read()
    if current == before:
        print("[OK] These animation settings are already restored.")
        return False
    if current.taskbar not in (before.taskbar, after.taskbar):
        raise ValueError("Restore conflict: taskbar settings changed after the backup.")
    print("Restore the previous Windows animation preferences for this account.")
    if apply:
        apply_animation_state(manager, current, before, directory)
    return True


class WindowsAnimations:
    def __init__(self, *, registry=None, user32=None):
        if registry is None:
            from xnebula.registry import WindowsRegistry

            registry = WindowsRegistry()
        self.registry = registry
        self.identity = registry.identity
        self.user32 = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        if user32 is None:
            self.user32.SystemParametersInfoW.argtypes = [
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_uint,
            ]
            self.user32.SystemParametersInfoW.restype = ctypes.c_int

    def _read_flag(self, flag):
        if flag.id == "minimize-restore":
            value = AnimationInfo(ctypes.sizeof(AnimationInfo), 0)
            size = value.cbSize
        else:
            value = ctypes.c_int()
            size = 0
        if not self.user32.SystemParametersInfoW(flag.get_action, size, ctypes.byref(value), 0):
            raise OSError(f"Windows could not read the {flag.id} animation preference.")
        return bool(value.iMinAnimate if isinstance(value, AnimationInfo) else value.value)

    def read(self):
        taskbar = self.registry.read(ANIMATION_TASKBAR)
        if taskbar is not None and taskbar.type != 4:
            raise ValueError("Unexpected taskbar animation preference type.")
        return AnimationState({flag.id: self._read_flag(flag) for flag in ANIMATION_FLAGS}, taskbar)

    def configure(self, before, after):
        decode_state(asdict(after))
        if self.read() != before:
            raise ValueError("Animation settings changed before applying them.")
        for flag in ANIMATION_FLAGS:
            enabled = after.values[flag.id]
            if flag.id == "minimize-restore":
                value = AnimationInfo(ctypes.sizeof(AnimationInfo), int(enabled))
                pointer, size = ctypes.byref(value), value.cbSize
            else:
                pointer, size = ctypes.c_void_p(int(enabled)), 0
            # Persist preferences and broadcast WM_SETTINGCHANGE to other apps.
            if not self.user32.SystemParametersInfoW(flag.set_action, size, pointer, 3):
                raise OSError(f"Windows could not change the {flag.id} animation preference.")
        self.registry.write(ANIMATION_TASKBAR, after.taskbar)
