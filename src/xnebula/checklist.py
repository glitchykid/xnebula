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
    if key in ("\r", "\x1b", "\x08"):
        return {"\r": "enter", "\x1b": "escape", "\x08": "backspace"}[key]
    return key if key.isprintable() else ""


def render_frame(
    rows,
    cursor,
    selected,
    *,
    query="",
    searching=False,
    selection_count=None,
    total=None,
    message="",
):
    width, height = shutil.get_terminal_size()
    width = max(1, width - 1)
    all_label = "shown" if query else "all"
    controls = f"A:{all_label} Space /:find Up/Down"
    headers = [
        f"Search: {query}{'_' if searching else ''}"
        if query or searching
        else "Search: / to filter",
        "Type filter | Enter:done Esc:clear" if searching else controls,
        "Enter:OK Esc:back",
    ][: max(0, height - 3)]
    capacity = max(1, height - len(headers) - 2)
    start = min(max(0, cursor - capacity // 2), max(0, len(rows) - capacity))
    lines = headers
    if not rows:
        lines.append("No matches; Esc:clear")
    for index in range(start, min(len(rows), start + capacity)):
        marker = ">" if index == cursor else " "
        check = "x" if index in selected else " "
        line = f"{marker} [{check}] {rows[index]}"[:width]
        lines.append(paint(line, "number") if index == cursor else line)
    if height > 2:
        count = len(selected) if selection_count is None else selection_count
        total = len(rows) if total is None else total
        position = f"{cursor + 1 if rows else 0}/{len(rows)}"
        lines.append(message or f"{count}/{total} selected | {len(rows)} matching | {position}")
    # A viewport prevents the active row from scrolling out of a small console.
    print(
        "\x1b[H\x1b[J" + "\n".join(line[:width] if "\x1b" not in line else line for line in lines),
        end="",
        flush=True,
    )


def select_items(rows, *, selected=None, read_key=None, render=None):
    if not rows:
        return None
    get_key = read_key or globals()["read_key"]
    draw = render or render_frame
    selected = set(selected or ())
    if any(type(index) is not int or not 0 <= index < len(rows) for index in selected):
        raise ValueError("Selected indexes must refer to displayed items.")
    cursor, query, searching, message = 0, "", False, ""
    native_screen = render is None
    if native_screen:
        if not enable_virtual_terminal():
            raise OSError("This terminal does not support the checklist display.")
        print("\x1b[?1049h\x1b[?25l", end="", flush=True)
    try:
        while True:
            matching = [
                index for index, name in enumerate(rows) if query.casefold() in name.casefold()
            ]
            draw(
                [rows[index] for index in matching],
                cursor,
                {position for position, index in enumerate(matching) if index in selected},
                query=query,
                searching=searching,
                selection_count=len(selected),
                total=len(rows),
                message=message,
            )
            key = get_key()
            message = ""
            if searching:
                if key == "enter":
                    searching = False
                elif key == "escape":
                    query, searching, cursor = "", False, 0
                elif key == "backspace":
                    query, cursor = query[:-1], 0
                elif len(key) == 1 and key.isprintable():
                    query, cursor = query + key, 0
                continue
            if key == "/":
                searching = True
                continue
            if key == "escape":
                if query:
                    query, cursor = "", 0
                    continue
                return None
            if key == "enter":
                if selected:
                    return sorted(selected)
                message = "Space: select an item | Esc: cancel"
            if not matching:
                continue
            if key == "up":
                cursor = (cursor - 1) % len(matching)
            elif key == "down":
                cursor = (cursor + 1) % len(matching)
            elif key == "home":
                cursor = 0
            elif key == "end":
                cursor = len(matching) - 1
            elif key in ("space", " "):
                selected.symmetric_difference_update({matching[cursor]})
            elif key in ("all", "a", "A"):
                if selected.issuperset(matching):
                    selected.difference_update(matching)
                else:
                    selected.update(matching)
    finally:
        if native_screen:
            print("\x1b[?25h\x1b[?1049l", end="", flush=True)
