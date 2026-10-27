"""Small, dependency-free terminal palette with plain-text output when redirected."""

import ctypes
import os
import sys

PALETTE = {
    "title": "1;36",
    "number": "36",
    "success": "92",
    "warning": "93",
    "error": "91",
    "muted": "90",
}


def color_enabled():
    if "NO_COLOR" in os.environ or not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.argtypes = [ctypes.c_uint]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    handle = kernel.GetStdHandle(-11)
    mode = ctypes.c_uint()
    return bool(
        kernel.GetConsoleMode(handle, ctypes.byref(mode))
        and kernel.SetConsoleMode(handle, mode.value | 4)
    )


def paint(text, style):
    return f"\x1b[{PALETTE[style]}m{text}\x1b[0m" if color_enabled() else text
