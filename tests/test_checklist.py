import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

from xnebula.checklist import read_key, render_frame, select_items


class ChecklistTests(unittest.TestCase):
    rows = ["Photos", "Store", "Xbox"]

    def choose(self, keys, rows=None, selected=None):
        frames = []

        def render(items, cursor, selected, **state):
            frames.append((list(items), cursor, set(selected)))

        result = select_items(
            self.rows if rows is None else rows,
            read_key=Mock(side_effect=keys),
            render=render,
            selected=selected,
        )
        return result, frames

    def test_space_toggles_current_row_and_enter_returns_display_order(self):
        result, frames = self.choose(["end", "space", "home", "space", "enter"])
        self.assertEqual(result, [0, 2])
        self.assertEqual(frames[0], (self.rows, 0, set()))
        self.assertEqual(frames[-1][2], {0, 2})
        self.assertEqual(self.choose(["space", "space", "enter", "escape"])[0], None)

    def test_navigation_wraps_at_both_ends(self):
        result, frames = self.choose(["up", "space", "down", "space", "enter"])
        self.assertEqual(result, [0, 2])
        self.assertIn((self.rows, 2, set()), frames)
        self.assertEqual(frames[-1][1], 0)

    def test_select_all_can_select_and_clear_every_item(self):
        self.assertEqual(self.choose(["all", "enter"])[0], [0, 1, 2])
        self.assertIsNone(self.choose(["all", "all", "enter", "escape"])[0])
        self.assertEqual(self.choose(["space", "all", "enter"])[0], [0, 1, 2])
        self.assertEqual(self.choose(["all", "space", "enter"])[0], [1, 2])

    def test_cancel_discards_selection_and_empty_enter_keeps_picker_open(self):
        self.assertIsNone(self.choose(["space", "escape"])[0])
        self.assertEqual(self.choose(["enter", "space", "enter"])[0], [0])

    def test_search_returns_original_indexes_and_preserves_hidden_selection(self):
        result, frames = self.choose(["space", "/", "x", "enter", "space", "enter"])
        self.assertEqual(result, [0, 2])
        self.assertIn((["Xbox"], 0, set()), frames)

    def test_unicode_search_is_case_insensitive_and_accepts_spaces_and_a(self):
        result, frames = self.choose(
            ["/", "Ф", "О", "Т", "О", " ", "A", "enter", "space", "enter"],
            ["Фото A", "Music"],
        )
        self.assertEqual(result, [0])
        self.assertEqual(frames[-1][0], ["Фото A"])

    def test_backspace_updates_filter_and_escape_clears_without_cancelling(self):
        result, frames = self.choose(
            ["/", "x", "q", "backspace", "enter", "escape", "space", "enter"]
        )
        self.assertEqual(result, [0])
        self.assertIn(([], 0, set()), frames)
        self.assertEqual(frames[-1][0], self.rows)

    def test_no_matches_navigation_and_select_all_do_not_change_selection(self):
        self.assertEqual(
            self.choose(
                ["/", "z", "enter", "up", "down", "home", "end", "space", "all", "enter"],
                selected=[1],
            )[0],
            [1],
        )

    def test_select_all_only_toggles_matches_and_keeps_hidden_selection(self):
        self.assertEqual(self.choose(["/", "x", "enter", "all", "enter"], selected=[0])[0], [0, 2])
        self.assertEqual(self.choose(["/", "x", "enter", "all", "enter"], selected=[0, 2])[0], [0])

    def test_initial_selection_is_copied_and_invalid_indexes_are_rejected(self):
        initial = [1]
        self.assertEqual(self.choose(["space", "enter"], selected=initial)[0], [0, 1])
        self.assertEqual(initial, [1])
        for selected in ([-1], [3], ["1"], [True]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.choose([], selected=selected)

    def test_empty_enter_shows_selection_guidance(self):
        renderer = Mock()
        select_items(self.rows, read_key=Mock(side_effect=["enter", "escape"]), render=renderer)
        self.assertIn("Space", renderer.call_args.kwargs["message"])
        self.assertIn("Esc", renderer.call_args.kwargs["message"])

    def test_escape_closes_empty_search_before_it_cancels_picker(self):
        self.assertEqual(self.choose(["/", "escape", "space", "enter"])[0], [0])
        self.assertIsNone(self.choose(["/", "escape", "escape"])[0])

    def test_search_ignores_navigation_keys_and_backspace_on_empty_query(self):
        result, frames = self.choose(["/", "up", "backspace", "down", "enter", "space", "enter"])
        self.assertEqual(result, [0])
        self.assertTrue(all(frame[0] == self.rows for frame in frames))

    def test_empty_list_does_not_read_keys_or_render(self):
        reader, renderer = Mock(), Mock()
        self.assertIsNone(select_items([], read_key=reader, render=renderer))
        reader.assert_not_called()
        renderer.assert_not_called()

    def test_unknown_keys_do_not_change_selection(self):
        self.assertEqual(self.choose(["unknown", "", "space", "enter"])[0], [0])

    def test_single_item_navigation_remains_in_range(self):
        result, frames = self.choose(["up", "down", "end", "home", "space", "enter"], ["Photos"])
        self.assertEqual(result, [0])
        self.assertTrue(all(frame[1] == 0 for frame in frames))

    def test_keyboard_interrupt_propagates_without_confirming_selection(self):
        with self.assertRaises(KeyboardInterrupt):
            self.choose(["space", KeyboardInterrupt()])


class ChecklistKeyTests(unittest.TestCase):
    def test_windows_extended_key_codes_decode_to_navigation(self):
        for prefix in ("\x00", "\xe0"):
            for code, expected in (("H", "up"), ("P", "down"), ("G", "home"), ("O", "end")):
                with (
                    self.subTest(prefix=prefix, code=code),
                    patch("msvcrt.getwch", side_effect=[prefix, code]),
                ):
                    self.assertEqual(read_key(), expected)

    def test_common_keys_decode_without_waiting_for_enter(self):
        for key, expected in (
            (" ", " "),
            ("a", "a"),
            ("A", "A"),
            ("/", "/"),
            ("Ф", "Ф"),
            ("\x08", "backspace"),
            ("\r", "enter"),
            ("\x1b", "escape"),
        ):
            with self.subTest(key=key), patch("msvcrt.getwch", return_value=key):
                self.assertEqual(read_key(), expected)

    def test_ctrl_c_raises_keyboard_interrupt(self):
        with patch("msvcrt.getwch", return_value="\x03"), self.assertRaises(KeyboardInterrupt):
            read_key()

    def test_unknown_key_does_not_trigger_an_action(self):
        for values in (["z"], ["\xe0", "K"]):
            with self.subTest(values=values), patch("msvcrt.getwch", side_effect=values):
                self.assertNotIn(
                    read_key(), ("space", "all", "enter", "escape", "up", "down", "home", "end")
                )


class ChecklistRenderingTests(unittest.TestCase):
    def frame(self, rows, cursor, selected, size, **state):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.checklist.shutil.get_terminal_size", return_value=size),
            patch.dict(os.environ, {"NO_COLOR": "1"}),
        ):
            render_frame(rows, cursor, selected, **state)
        return output.getvalue()

    def test_search_displays_filter_visible_bulk_scope_and_total_selection(self):
        output = self.frame(["Xbox"], 0, {0}, (80, 12), query="x", total=3, selection_count=2)
        self.assertIn("Search: x", output)
        self.assertIn("A:shown", output)
        self.assertIn("2/3 selected | 1 matching", output)

    def test_search_editing_and_no_matches_render_without_cursor_row(self):
        output = self.frame([], 0, set(), (80, 12), query="missing", searching=True)
        self.assertIn("Search: missing_", output)
        self.assertIn("Enter:done Esc:clear", output)
        self.assertIn("No matches", output)
        self.assertIn("0/0", output)
        self.assertNotIn("> [", output)

    def test_search_frames_fit_narrow_and_tiny_terminal(self):
        for height in range(1, 7):
            for rows in ([], ["Фото A"]):
                with self.subTest(height=height, rows=rows):
                    output = self.frame(rows, 0, set(), (20, height), query="Фото A")
                    lines = output.removeprefix("\x1b[H\x1b[J").splitlines()
                    self.assertLessEqual(len(lines), max(1, height - 1))
                    self.assertTrue(all(len(line) <= 19 for line in lines))
                    if height >= 5:
                        self.assertIn("A:shown", output)

    def test_viewport_keeps_current_row_visible_at_start_middle_and_end(self):
        rows = [f"App {number}" for number in range(20)]
        for cursor in (0, 10, 19):
            with self.subTest(cursor=cursor):
                output = self.frame(rows, cursor, {cursor}, (80, 10))
                self.assertIn(f"> [x] App {cursor}\n", output)
                self.assertIn("selected", output)
                self.assertIn(f"{cursor + 1}/20", output)
                self.assertLessEqual(len(output.splitlines()), 9)

    def test_long_names_and_instructions_fit_terminal_width(self):
        output = self.frame(["A" * 200], 0, set(), (20, 10))
        self.assertTrue(
            all(len(line) <= 19 for line in output.removeprefix("\x1b[H\x1b[J").splitlines())
        )
        self.assertIn("> [ ] " + "A" * 13, output)

    def test_tiny_terminal_still_renders_one_active_row(self):
        for height in range(1, 6):
            with self.subTest(height=height):
                output = self.frame(["Photos", "Store"], 1, set(), (20, height))
                lines = output.removeprefix("\x1b[H\x1b[J").splitlines()
                self.assertLessEqual(len(lines), max(1, height - 1))
                self.assertIn("> [ ] Store", lines)

    def test_no_color_keeps_check_marks_and_cursor_without_color_sequences(self):
        output = self.frame(["Photos"], 0, {0}, (80, 10))
        self.assertIn("> [x] Photos", output)
        self.assertNotIn("\x1b[36m", output)

    def test_native_screen_restores_cursor_and_original_screen_after_enter(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.checklist.enable_virtual_terminal", return_value=True),
            patch("xnebula.checklist.render_frame") as render,
        ):
            self.assertEqual(
                select_items(["Photos"], read_key=Mock(side_effect=["space", "enter"])), [0]
            )
        self.assertEqual(render.call_count, 2)
        self.assertEqual(output.getvalue(), "\x1b[?1049h\x1b[?25l\x1b[?25h\x1b[?1049l")

    def test_native_screen_cleanup_runs_after_key_or_render_error(self):
        for failure in ("key", "render"):
            with (
                self.subTest(failure=failure),
                contextlib.redirect_stdout(io.StringIO()) as output,
                patch("xnebula.checklist.enable_virtual_terminal", return_value=True),
                patch(
                    "xnebula.checklist.render_frame",
                    side_effect=OSError("render failed") if failure == "render" else None,
                ),
                self.assertRaises((KeyboardInterrupt, OSError)),
            ):
                select_items(["Photos"], read_key=Mock(side_effect=KeyboardInterrupt()))
            self.assertTrue(output.getvalue().endswith("\x1b[?25h\x1b[?1049l"))

    def test_unsupported_terminal_rejects_before_reading_or_entering_screen(self):
        reader = Mock()
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("xnebula.checklist.enable_virtual_terminal", return_value=False),
            self.assertRaisesRegex(OSError, "does not support"),
        ):
            select_items(["Photos"], read_key=reader)
        reader.assert_not_called()
        self.assertEqual(output.getvalue(), "")
