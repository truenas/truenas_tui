"""
Full-screen form for editing a set of named fields.

Layout (takes over the whole content area passed in):

  ┌─ Title ──────────────────────────────┐
  │                                      │
  │  Section Title                       │
  │  ─────────────────────────────────   │
  │  Field Label   : [value            ] │
  │  Bool Field    : [Yes               ]│
  │  Choice Field  : [< Option >        ]│
  │  Int Field     : [1500              ]│
  │  List Field    : [(3 items) [Enter] ]│
  │  ...                                 │
  │                                      │
  │  Help text for the currently focused │
  │  [ Save ]   [ Cancel ]               │
  │  Tab/↑↓: navigate  Enter: edit/next  │
  └──────────────────────────────────────┘

Field types:

  FormField   – plain text input
  BoolField   – True/False toggle; run() returns bool
  ChoiceField – dropdown; Left/Right cycle, Enter opens select_dialog;
                run() returns the chosen string
  IntField    – digits-only text; optional min/max; run() returns int
  SectionField– non-editable bold header + separator line; skipped by Tab
  ListField   – variable-length list; Enter opens sub-editor;
                run() returns list[str]

Usage::

    fields = [
        SectionField(key='', label='Network'),
        FormField(key='hostname', label='Hostname', value=current_value),
        BoolField(key='dhcp', label='Use DHCP', value=True),
        ChoiceField(key='proto', label='Protocol', choices=['TCP', 'UDP']),
        IntField(key='mtu', label='MTU', value=1500, min_val=68, max_val=9000),
        ListField(key='aliases', label='Aliases'),
    ]
    form = Form(stdscr, 'Network Settings', fields)
    result = form.run()   # returns dict {key: typed_value} or None if cancelled
"""

import curses
from dataclasses import dataclass, field
from typing import Any, Callable

from truenas_tui.localization import TRANSLATE

from . import HardExit, colors
from .colors import pair
from .dialogs import confirm_dialog, input_dialog, message_dialog, select_dialog

_ENTER = (ord("\n"), ord("\r"))


@dataclass(slots=True, kw_only=True, frozen=True)
class FormField:
    key: str
    label: str
    value: str = ""
    secret: bool = False
    readonly: bool = False
    # Optionally validate; return error string or None
    validator: Any = field(default=None, repr=False)
    help_text: str = ""


@dataclass(slots=True, kw_only=True, frozen=True)
class BoolField(FormField):
    """Toggle True/False.  Space / Left / Right / Enter all flip the value."""

    value: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class ChoiceField(FormField):
    """Pick one of N string options.
    Left/Right cycle in-place; Enter opens select_dialog() for longer lists.
    run() returns the chosen string from choices (not labels, not index).
    Optional labels provides display strings parallel to choices; if omitted,
    choices strings are displayed directly."""

    value: int = 0  # index into choices
    choices: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass(slots=True, kw_only=True, frozen=True)
class IntField(FormField):
    """Numeric text input; non-digit keystrokes are silently dropped.
    Optional inclusive bounds validated on save.  run() returns int."""

    value: int | str = 0
    min_val: int | None = None
    max_val: int | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class SectionField(FormField):
    """Non-editable visual separator with a bold section title and a
    dimmed rule below it.  Skipped entirely by Tab / arrow navigation."""

    readonly: bool = True


@dataclass(slots=True, kw_only=True, frozen=True)
class ListField(FormField):
    """Variable-length list of strings.
    Activating with Enter opens a full-screen list sub-editor.
    run() returns list[str]."""

    value: list[str] = field(default_factory=list)
    item_label: str = "Item"
    item_validator: Callable[[str], str | None] | None = field(default=None, repr=False)


def _is_text(f: FormField) -> bool:
    """FormField and IntField are edited through a text buffer."""
    return not isinstance(f, (BoolField, ChoiceField, SectionField, ListField))


def _initial_state(f: FormField):
    if isinstance(f, BoolField):
        return bool(f.value)
    if isinstance(f, ChoiceField):
        return int(f.value)
    if isinstance(f, ListField):
        return list(f.value)
    if isinstance(f, SectionField):
        return None
    return list(str(f.value))


class Form:
    LABEL_W = 20  # Width reserved for labels

    def __init__(self, stdscr, title: str, fields: list[FormField]):
        self.stdscr = stdscr
        self.title = title
        self.fields = fields
        self._error: str = ""
        # Per-field editable value: list of characters for text fields, bool
        # for BoolField, chosen index for ChoiceField, list of items for ListField.
        self._state: list = []
        self._cursors = []
        for f in fields:
            s = _initial_state(f)
            self._state.append(s)
            self._cursors.append(len(s) if _is_text(f) else 0)
        self._scrolls = [0] * len(fields)
        self._field_errors = [""] * len(fields)
        # Start on the first non-section field
        self._cursor_field = 0
        for i, f in enumerate(fields):
            if not isinstance(f, SectionField):
                self._cursor_field = i
                break

    def run(self) -> dict | None:
        """
        Run the form event loop.
        Returns a dict of {key: typed_value} on save, or None on cancel.
        """
        self.stdscr.keypad(True)
        save_idx = len(self.fields)
        cancel_idx = save_idx + 1

        while True:
            self._draw()
            key = self.stdscr.getch()
            cur = self._cursor_field

            if key == 4:  # Ctrl+D → hard exit
                curses.curs_set(0)
                raise HardExit()
            if key == 27 or (key in _ENTER and cur == cancel_idx):  # Esc / Cancel
                curses.curs_set(0)
                return None
            if key in (curses.KEY_UP, curses.KEY_BTAB):
                self._cursor_field = self._advance(cur, -1)
            elif key in (curses.KEY_DOWN, ord("\t")):
                self._cursor_field = self._advance(cur, +1)
            elif key in _ENTER and cur == save_idx:
                result = self._collect()
                self._error = self._validate(result)
                if not self._error:
                    curses.curs_set(0)
                    return result
            elif cur < save_idx:
                self._field_key(cur, key)

    def _field_key(self, idx: int, key: int) -> None:
        """Apply a keypress to the field at idx."""
        f = self.fields[idx]
        enter = key in _ENTER
        if isinstance(f, SectionField):
            return
        if isinstance(f, BoolField):
            if enter or (
                not f.readonly and key in (ord(" "), curses.KEY_LEFT, curses.KEY_RIGHT)
            ):
                self._state[idx] = not self._state[idx]
        elif isinstance(f, ChoiceField):
            n = len(f.choices)
            if enter and n:
                pick = select_dialog(
                    self.stdscr, f.label, f.labels or f.choices, self._state[idx]
                )
                if pick is not None:
                    self._state[idx] = pick
            elif key == curses.KEY_LEFT and n and not f.readonly:
                self._state[idx] = (self._state[idx] - 1) % n
            elif key == curses.KEY_RIGHT and n and not f.readonly:
                self._state[idx] = (self._state[idx] + 1) % n
        elif isinstance(f, ListField):
            if enter:
                self._state[idx] = self._run_list_editor(idx)
        elif enter:
            self._cursor_field = self._advance(idx, +1)
        elif not f.readonly:
            self._text_key(idx, key)
            self._field_errors[idx] = ""
        self._error = ""

    def _advance(self, cur: int, direction: int) -> int:
        """Move focus index by direction (+1/-1), skipping SectionFields."""
        n_items = len(self.fields) + 2
        new = (cur + direction) % n_items
        while new < len(self.fields) and isinstance(self.fields[new], SectionField):
            new = (new + direction) % n_items
        return new

    def _draw(self) -> None:
        stdscr = self.stdscr
        stdscr.erase()
        sh, sw = stdscr.getmaxyx()

        field_w = max(sw - self.LABEL_W - 6, 10)
        field_x = 2 + self.LABEL_W + 2

        # Title
        title_str = f"  {self.title}  "
        try:
            stdscr.addstr(
                0,
                max(0, (sw - len(title_str)) // 2),
                title_str,
                pair(colors.HEADER) | curses.A_BOLD,
            )
        except curses.error:
            pass

        # Top separator
        try:
            stdscr.addstr(1, 0, "─" * sw, pair(colors.BORDER))
        except curses.error:
            pass

        start_y = 3
        y = start_y
        cursor_y = cursor_x = -1  # hardware cursor position for text fields

        for i, f in enumerate(self.fields):
            if y >= sh - 4:
                break
            active = self._cursor_field == i

            if isinstance(f, SectionField):
                try:
                    stdscr.addstr(y, 2, f.label[: sw - 3], curses.A_BOLD)
                    if y + 1 < sh - 4:
                        stdscr.addstr(
                            y + 1,
                            2,
                            "─" * max(0, sw - 4),
                            pair(colors.DIM),
                        )
                except curses.error:
                    pass
                y += 2
                continue

            attr = (
                pair(colors.MENU_SELECTED) | curses.A_BOLD
                if active
                else curses.A_NORMAL
            )
            if isinstance(f, BoolField):
                text = TRANSLATE("Yes") if self._state[i] else TRANSLATE("No")
            elif isinstance(f, ChoiceField):
                chosen = (f.labels or f.choices)[self._state[i]] if f.choices else ""
                text = f"< {chosen} >" if active else chosen
            elif isinstance(f, ListField):
                n = len(self._state[i])
                summary = f"({n} item{'s' if n != 1 else ''})" if n else "(empty)"
                text = f"{summary}  [Enter to edit]"
            else:
                buf = self._state[i]
                display = "*" * len(buf) if f.secret else "".join(buf)
                text = display[self._scrolls[i] : self._scrolls[i] + field_w]
                if self._field_errors[i]:
                    attr = pair(colors.ERROR) | curses.A_BOLD
                if active and not f.readonly:
                    cursor_y = y
                    cursor_x = field_x + 1 + (self._cursors[i] - self._scrolls[i])
            try:
                stdscr.addstr(
                    y,
                    2,
                    f"{f.label[: self.LABEL_W - 1]:<{self.LABEL_W}}",
                    curses.A_BOLD if active else pair(colors.DIM),
                )
                stdscr.addstr(y, field_x, f"[{text:<{field_w}}]", attr)
            except curses.error:
                pass
            y += 1

        # Buttons row, with the focused field's help text on the row above it
        total = 0
        for f in self.fields:
            total += 2 if isinstance(f, SectionField) else 1
        btn_y = start_y + total + 1
        cf = self._cursor_field
        help_text = self.fields[cf].help_text if cf < len(self.fields) else ""
        if help_text and start_y <= btn_y - 1 < sh - 2:
            try:
                stdscr.addstr(btn_y - 1, 2, help_text[: sw - 3], pair(colors.DIM))
            except curses.error:
                pass

        if btn_y < sh - 2:
            focus = pair(colors.MENU_SELECTED) | curses.A_BOLD
            save_idx = len(self.fields)
            try:
                stdscr.addstr(
                    btn_y,
                    4,
                    f"[ {TRANSLATE('Save')} ]",
                    focus if cf == save_idx else curses.A_NORMAL,
                )
                stdscr.addstr(
                    btn_y,
                    16,
                    f"[ {TRANSLATE('Cancel')} ]",
                    focus if cf == save_idx + 1 else curses.A_NORMAL,
                )
            except curses.error:
                pass

        # Navigation hint
        hint = TRANSLATE("Tab/↑↓: navigate   Enter: confirm   Esc: cancel")
        if sh > 2:
            try:
                stdscr.addstr(sh - 2, 2, hint[: sw - 3], pair(colors.DIM))
            except curses.error:
                pass

        # Error message
        if self._error and sh > 1:
            try:
                stdscr.addstr(
                    sh - 1,
                    2,
                    self._error[: sw - 3],
                    pair(colors.ERROR) | curses.A_BOLD,
                )
            except curses.error:
                pass

        # Show / hide hardware cursor
        if cursor_y >= 0:
            curses.curs_set(1)
            try:
                stdscr.move(cursor_y, cursor_x)
            except curses.error:
                pass
        else:
            curses.curs_set(0)

        stdscr.refresh()

    def _text_key(self, idx: int, key: int) -> None:
        buf = self._state[idx]
        cursor = self._cursors[idx]
        field_w = max(self.stdscr.getmaxyx()[1] - self.LABEL_W - 6, 10)

        if key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor > 0:
                del buf[cursor - 1]
                cursor -= 1
        elif key == curses.KEY_DC:
            if cursor < len(buf):
                del buf[cursor]
        elif key == curses.KEY_LEFT:
            cursor = max(0, cursor - 1)
        elif key == curses.KEY_RIGHT:
            cursor = min(len(buf), cursor + 1)
        elif key in (curses.KEY_HOME, 1):  # Home / Ctrl+A
            cursor = 0
        elif key in (curses.KEY_END, 5):  # End / Ctrl+E
            cursor = len(buf)
        elif key == 21:  # Ctrl+U – clear
            buf.clear()
            cursor = 0
        elif 32 <= key < 256:
            ch = chr(key)
            # IntField accepts digits and a leading minus sign only
            if (
                not isinstance(self.fields[idx], IntField)
                or ch.isdigit()
                or (ch == "-" and not buf)
            ):
                buf.insert(cursor, ch)
                cursor += 1

        # Update horizontal scroll
        scroll = self._scrolls[idx]
        if cursor - scroll >= field_w:
            scroll = cursor - field_w + 1
        elif cursor < scroll:
            scroll = cursor
        self._cursors[idx] = cursor
        self._scrolls[idx] = scroll

    def _run_list_editor(self, field_idx: int) -> list[str]:
        """Full-screen inline list editor for a ListField.
        Temporarily replaces the form until Esc is pressed.
        Returns the (possibly modified) list."""
        f = self.fields[field_idx]
        items = list(self._state[field_idx])
        current = 0
        scroll_top = 0
        stdscr = self.stdscr
        curses.curs_set(0)
        stdscr.keypad(True)

        while True:
            stdscr.erase()
            sh, sw = stdscr.getmaxyx()
            visible_rows = max(1, sh - 7)

            # Title
            title_str = f"  {f.label}  "
            try:
                stdscr.addstr(
                    0,
                    max(0, (sw - len(title_str)) // 2),
                    title_str,
                    pair(colors.HEADER) | curses.A_BOLD,
                )
                stdscr.addstr(1, 0, "─" * sw, pair(colors.BORDER))
            except curses.error:
                pass

            # Clamp current and update scroll
            if items:
                current = max(0, min(current, len(items) - 1))
                if current < scroll_top:
                    scroll_top = current
                elif current >= scroll_top + visible_rows:
                    scroll_top = current - visible_rows + 1
            else:
                scroll_top = 0

            start_y = 3
            if not items:
                try:
                    stdscr.addstr(start_y, 2, "(empty list)", pair(colors.DIM))
                except curses.error:
                    pass
            else:
                for i in range(visible_rows):
                    idx = scroll_top + i
                    if idx >= len(items):
                        break
                    y = start_y + i
                    if y >= sh - 4:
                        break
                    attr = (
                        pair(colors.MENU_SELECTED) | curses.A_BOLD
                        if idx == current
                        else curses.A_NORMAL
                    )
                    try:
                        stdscr.addstr(y, 2, f"{items[idx]:<{max(1, sw - 5)}}", attr)
                    except curses.error:
                        pass

            # Footer hint
            footer = TRANSLATE(
                "[↑↓] Select  [Enter] Edit  [a] Add  [d] Delete  [Esc] Done"
            )
            try:
                stdscr.addstr(sh - 2, 2, footer[: sw - 3], pair(colors.DIM))
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == 4:  # Ctrl+D
                curses.curs_set(1)
                raise HardExit()
            elif key == 27:  # Esc – done
                break
            elif key == curses.KEY_UP and items:
                current = max(0, current - 1)
            elif key == curses.KEY_DOWN and items:
                current = min(len(items) - 1, current + 1)
            elif key in (ord("a"), ord("A")):  # Add
                val = input_dialog(
                    stdscr, f"Add {f.item_label}", f"Enter {f.item_label}:"
                )
                if val is not None:
                    err = f.item_validator(val) if f.item_validator else None
                    if err:
                        message_dialog(stdscr, "Error", err)
                    else:
                        items.append(val)
                        current = len(items) - 1
            elif key in (ord("d"), ord("D")) and items:  # Delete
                if confirm_dialog(
                    stdscr, "Confirm Delete", f'Delete "{items[current]}"?'
                ):
                    del items[current]
                    current = max(0, min(current, len(items) - 1))
            elif key in _ENTER and items:  # Edit
                val = input_dialog(
                    stdscr,
                    f"Edit {f.item_label}",
                    f"Edit {f.item_label}:",
                    default=items[current],
                )
                if val is not None:
                    err = f.item_validator(val) if f.item_validator else None
                    if err:
                        message_dialog(stdscr, "Error", err)
                    else:
                        items[current] = val

        curses.curs_set(1)
        return items

    def _collect(self) -> dict:
        result: dict[str, Any] = {}
        for f, state in zip(self.fields, self._state):
            if isinstance(f, SectionField):
                continue
            if isinstance(f, ChoiceField):
                result[f.key] = f.choices[state] if f.choices else ""
            elif isinstance(f, IntField):
                s = "".join(state).strip()
                try:
                    result[f.key] = int(s) if s else 0
                except ValueError:
                    result[f.key] = s  # invalid; _validate will catch it
            elif isinstance(f, BoolField):
                result[f.key] = state
            elif isinstance(f, ListField):
                result[f.key] = list(state)
            else:
                result[f.key] = "".join(state)
        return result

    def _validate(self, data: dict) -> str:
        """Return first validation error string, or empty string if OK."""
        # Clear per-field error highlighting before re-checking
        self._field_errors = [""] * len(self.fields)
        for i, f in enumerate(self.fields):
            if isinstance(f, SectionField):
                continue
            if isinstance(f, IntField):
                val = data.get(f.key)
                if not isinstance(val, int):
                    err = f'"{f.label}" must be a whole number'
                elif f.min_val is not None and val < f.min_val:
                    err = f'"{f.label}" must be ≥ {f.min_val}'
                elif f.max_val is not None and val > f.max_val:
                    err = f'"{f.label}" must be ≤ {f.max_val}'
                else:
                    err = ""
                if err:
                    self._field_errors[i] = err
                    return err
            if f.validator:
                err = f.validator(data.get(f.key, ""))
                if err:
                    return err
        return ""
