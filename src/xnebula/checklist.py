"""Keyboard checklist for a Windows terminal; no third-party dependencies."""

import shutil

from xnebula.console import enable_virtual_terminal, paint


def read_key():
    import msvcrt

    key = msvcrt.getwch()
    if key in ("\x00", "\xe0"):
        return {"H": "up", "P": "down", "G": "home", "O": "end"}.get(msvcrt.getwch(), "")
    if key == "\x03":
        raise KeyboardInterrupt
    return {" ": "space", "a": "all", "\r": "enter", "\x1b": "escape"}.get(key.lower(), "")


def render_frame(rows, cursor, selected):
    width, height = shutil.get_terminal_size()
    width = max(1, width - 1)
    headers = [
        "Up/Down Space A:all" if width < 40 else "Up/Down: move  Space: toggle  A: all/none",
        "Enter:OK Esc:back",
    ][: max(0, height - 3)]
    capacity = max(1, height - len(headers) - 2)
    start = min(max(0, cursor - capacity // 2), max(0, len(rows) - capacity))
    lines = headers
    for index in range(start, min(len(rows), start + capacity)):
        marker = ">" if index == cursor else " "
        check = "x" if index in selected else " "
        line = f"{marker} [{check}] {rows[index]}"[:width]
        lines.append(paint(line, "number") if index == cursor else line)
    if height > 2:
        lines.append(f"{len(selected)}/{len(rows)} selected | {cursor + 1}/{len(rows)}")
    # A viewport prevents the active row from scrolling out of a small console.
    print(
        "\x1b[H\x1b[J" + "\n".join(line[:width] if "\x1b" not in line else line for line in lines),
        end="",
        flush=True,
    )


def select_items(rows, *, read_key=None, render=None):
    if not rows:
        return None
    get_key = read_key or globals()["read_key"]
    draw = render or render_frame
    cursor, selected = 0, set()
    native_screen = render is None
    if native_screen:
        if not enable_virtual_terminal():
            raise OSError("This terminal does not support the checklist display.")
        print("\x1b[?1049h\x1b[?25l", end="", flush=True)
    try:
        while True:
            draw(rows, cursor, selected.copy())
            key = get_key()
            if key == "escape":
                return None
            if key == "enter":
                return sorted(selected) or None
            if key == "up":
                cursor = (cursor - 1) % len(rows)
            elif key == "down":
                cursor = (cursor + 1) % len(rows)
            elif key == "home":
                cursor = 0
            elif key == "end":
                cursor = len(rows) - 1
            elif key == "space":
                selected.symmetric_difference_update({cursor})
            elif key == "all":
                selected = set() if len(selected) == len(rows) else set(range(len(rows)))
    finally:
        if native_screen:
            print("\x1b[?25h\x1b[?1049l", end="", flush=True)
