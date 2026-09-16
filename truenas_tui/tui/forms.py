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

  FormField   – plain text input (original behaviour, unchanged)
  BoolField   – True/False toggle; run() returns bool
  ChoiceField – dropdown; Left/Right cycle, Enter opens select_dialog;
                run() returns the chosen string
  IntField    – digits-only text; optional min/max; run() returns int
  SectionField– non-editable bold header + separator line; skipped by Tab
  ListField   – variable-length list; Enter opens sub-editor;
                run() returns list[str]

All new types subclass FormField, so existing code using bare FormField
instances is 100% unaffected.  run() return type broadens from
dict[str, str] to dict[str, Any].

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
from .dialogs import confirm_dialog, input_dialog, message_dialog, select_dialog


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


class Form:
    LABEL_W = 20  # Width reserved for labels

    def __init__(self, stdscr, title: str, fields: list[FormField]):
        self.stdscr = stdscr
        self.title = title
        self.fields = fields
        self._error: str = ""

        # Per-field mutable state (parallel arrays, one entry per field)
        self._field_bufs: list[list[str]] = []  # text buffer (FormField, IntField)
        self._field_cursors: list[int] = []  # text cursor position
        self._field_scrolls: list[int] = []  # horizontal scroll offset
        self._bool_vals: list[bool] = []  # BoolField current value
        self._choice_idxs: list[int] = []  # ChoiceField selected index
        self._list_vals: list[list[str]] = []  # ListField current list
        self._field_errors: list[str] = []  # per-field error (IntField bounds)

        for f in fields:
            if isinstance(f, BoolField):
                self._field_bufs.append([])
                self._field_cursors.append(0)
                self._field_scrolls.append(0)
                self._bool_vals.append(bool(f.value))
                self._choice_idxs.append(0)
                self._list_vals.append([])
            elif isinstance(f, ChoiceField):
                self._field_bufs.append([])
                self._field_cursors.append(0)
                self._field_scrolls.append(0)
                self._bool_vals.append(False)
                self._choice_idxs.append(int(f.value))
                self._list_vals.append([])
            elif isinstance(f, IntField):
                s = str(f.value)
                self._field_bufs.append(list(s))
                self._field_cursors.append(len(s))
                self._field_scrolls.append(0)
                self._bool_vals.append(False)
                self._choice_idxs.append(0)
                self._list_vals.append([])
            elif isinstance(f, (SectionField, ListField)):
                self._field_bufs.append([])
                self._field_cursors.append(0)
                self._field_scrolls.append(0)
                self._bool_vals.append(False)
                self._choice_idxs.append(0)
                self._list_vals.append(
                    list(f.value) if isinstance(f, ListField) else []
                )
            else:
                # Plain FormField
                s = str(f.value)
                self._field_bufs.append(list(s))
                self._field_cursors.append(len(s))
                self._field_scrolls.append(0)
                self._bool_vals.append(False)
                self._choice_idxs.append(0)
                self._list_vals.append([])
            self._field_errors.append("")

        # Start on the first non-section navigable field
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

        SAVE_IDX = len(self.fields)
        CANCEL_IDX = len(self.fields) + 1

        while True:
            self._draw()
            key = self.stdscr.getch()

            cur = self._cursor_field

            if key == 4:  # Ctrl+D → hard exit
                curses.curs_set(0)
                raise HardExit()
            elif key == 27:  # Esc → cancel
                curses.curs_set(0)
                return None

            elif key in (curses.KEY_UP, curses.KEY_BTAB):
                self._cursor_field = self._advance(cur, -1)

            elif key in (curses.KEY_DOWN, ord("\t")):
                self._cursor_field = self._advance(cur, +1)

            elif key in (ord("\n"), ord("\r")):
                if cur == SAVE_IDX:
                    result = self._collect()
                    err = self._validate(result)
                    if err:
                        self._error = err
                    else:
                        curses.curs_set(0)
                        return result
                elif cur == CANCEL_IDX:
                    curses.curs_set(0)
                    return None
                elif 0 <= cur < len(self.fields):
                    f = self.fields[cur]
                    if isinstance(f, BoolField):
                        self._bool_vals[cur] = not self._bool_vals[cur]
                        self._error = ""
                    elif isinstance(f, ChoiceField):
                        if f.choices:
                            display_list = f.labels if f.labels else f.choices
                            idx = select_dialog(
                                self.stdscr,
                                f.label,
                                display_list,
                                self._choice_idxs[cur],
                            )
                            if idx is not None:
                                self._choice_idxs[cur] = idx
                        self._error = ""
                    elif isinstance(f, ListField):
                        self._list_vals[cur] = self._run_list_editor(cur)
                        self._error = ""
                    elif isinstance(f, SectionField):
                        pass
                    else:
                        # FormField / IntField → advance to next
                        self._cursor_field = self._advance(cur, +1)

            else:
                # Delegate to per-field key handler
                if 0 <= cur < len(self.fields):
                    f = self.fields[cur]
                    if isinstance(f, BoolField) and not f.readonly:
                        if key in (ord(" "), curses.KEY_LEFT, curses.KEY_RIGHT):
                            self._bool_vals[cur] = not self._bool_vals[cur]
                            self._error = ""
                    elif isinstance(f, ChoiceField) and not f.readonly:
                        if key == curses.KEY_LEFT and f.choices:
                            self._choice_idxs[cur] = (self._choice_idxs[cur] - 1) % len(
                                f.choices
                            )
                            self._error = ""
                        elif key == curses.KEY_RIGHT and f.choices:
                            self._choice_idxs[cur] = (self._choice_idxs[cur] + 1) % len(
                                f.choices
                            )
                            self._error = ""
                    elif not isinstance(
                        f, (BoolField, ChoiceField, SectionField, ListField)
                    ):
                        # FormField or IntField
                        if not f.readonly:
                            self._field_handle_key(cur, key)

    def _advance(self, cur: int, direction: int) -> int:
        """Move focus index by direction (+1/-1), skipping SectionFields."""
        n_items = len(self.fields) + 2
        new = (cur + direction) % n_items
        visited: set[int] = set()
        while (
            new not in visited
            and new < len(self.fields)
            and isinstance(self.fields[new], SectionField)
        ):
            visited.add(new)
            new = (new + direction) % n_items
        return new

    def _compute_field_y_offsets(self) -> list[int]:
        """Return y-offset (relative to start_y) for each field index."""
        offsets: list[int] = []
        y = 0
        for f in self.fields:
            offsets.append(y)
            y += 2 if isinstance(f, SectionField) else 1
        return offsets

    def _total_fields_height(self) -> int:
        return sum(2 if isinstance(f, SectionField) else 1 for f in self.fields)

    def _draw(self) -> None:
        stdscr = self.stdscr
        stdscr.erase()
        sh, sw = stdscr.getmaxyx()

        field_w = max(sw - self.LABEL_W - 6, 10)

        # Title
        title_str = f"  {self.title}  "
        stdscr.addstr(
            0,
            max(0, (sw - len(title_str)) // 2),
            title_str,
            curses.color_pair(colors.HEADER) | curses.A_BOLD,
        )

        # Top separator
        try:
            stdscr.addstr(1, 0, "─" * sw, curses.color_pair(colors.BORDER))
        except curses.error:
            pass

        start_y = 3
        y_offsets = self._compute_field_y_offsets()
        SAVE_IDX = len(self.fields)
        CANCEL_IDX = len(self.fields) + 1

        # Track where to place the text cursor (for FormField / IntField)
        cursor_y = cursor_x = -1

        for i, f in enumerate(self.fields):
            y = start_y + y_offsets[i]
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
                            curses.color_pair(colors.DIM),
                        )
                except curses.error:
                    pass
                continue

            label = f"{f.label[: self.LABEL_W - 1]:<{self.LABEL_W}}"
            label_attr = curses.A_BOLD if active else curses.A_DIM

            if isinstance(f, BoolField):
                val_str = TRANSLATE("Yes") if self._bool_vals[i] else TRANSLATE("No")
                field_str = f"[{val_str:<{field_w}}]"
                attr = (
                    curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                    if active
                    else curses.A_NORMAL
                )
                try:
                    stdscr.addstr(y, 2, label, label_attr)
                    stdscr.addstr(y, 2 + self.LABEL_W + 2, field_str, attr)
                except curses.error:
                    pass

            elif isinstance(f, ChoiceField):
                idx_c = self._choice_idxs[i]
                chosen = (
                    (f.labels[idx_c] if f.labels else f.choices[idx_c])
                    if f.choices
                    else ""
                )
                display = f"< {chosen} >" if active else chosen
                field_str = f"[{display:<{field_w}}]"
                attr = (
                    curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                    if active
                    else curses.A_NORMAL
                )
                try:
                    stdscr.addstr(y, 2, label, label_attr)
                    stdscr.addstr(y, 2 + self.LABEL_W + 2, field_str, attr)
                except curses.error:
                    pass

            elif isinstance(f, ListField):
                n = len(self._list_vals[i])
                summary = (
                    f"({n} item{'s' if n != 1 else ''})  [Enter to edit]"
                    if n
                    else "(empty)  [Enter to edit]"
                )
                field_str = f"[{summary:<{field_w}}]"
                attr = (
                    curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                    if active
                    else curses.A_NORMAL
                )
                try:
                    stdscr.addstr(y, 2, label, label_attr)
                    stdscr.addstr(y, 2 + self.LABEL_W + 2, field_str, attr)
                except curses.error:
                    pass

            else:
                # FormField / IntField (text-based)
                buf = self._field_bufs[i]
                cur_pos = self._field_cursors[i]
                scroll = self._field_scrolls[i]
                display = ("*" * len(buf)) if f.secret else "".join(buf)
                visible = display[scroll : scroll + field_w]
                field_str = f"[{visible:<{field_w}}]"
                if self._field_errors[i]:
                    attr = curses.color_pair(colors.ERROR) | curses.A_BOLD
                elif active:
                    attr = curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                else:
                    attr = curses.A_NORMAL
                try:
                    stdscr.addstr(y, 2, label, label_attr)
                    stdscr.addstr(y, 2 + self.LABEL_W + 2, field_str, attr)
                except curses.error:
                    pass
                if active and not f.readonly:
                    cursor_y = y
                    cursor_x = 2 + self.LABEL_W + 2 + 1 + (cur_pos - scroll)

        # Buttons row
        btn_y = start_y + self._total_fields_height() + 1

        # Help text row (the blank row between last field and buttons)
        help_row = btn_y - 1
        cf = self._cursor_field
        if 0 <= cf < len(self.fields) and start_y <= help_row < sh - 2:
            ht = self.fields[cf].help_text
            if ht:
                try:
                    stdscr.addstr(
                        help_row, 2, ht[: sw - 3], curses.color_pair(colors.DIM)
                    )
                except curses.error:
                    pass

        if btn_y < sh - 2:
            save_attr = (
                curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                if self._cursor_field == SAVE_IDX
                else curses.A_NORMAL
            )
            cancel_attr = (
                curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
                if self._cursor_field == CANCEL_IDX
                else curses.A_NORMAL
            )
            try:
                stdscr.addstr(btn_y, 4, f"[ {TRANSLATE('Save')} ]", save_attr)
                stdscr.addstr(btn_y, 16, f"[ {TRANSLATE('Cancel')} ]", cancel_attr)
            except curses.error:
                pass

        # Navigation hint
        hint = TRANSLATE("Tab/↑↓: navigate   Enter: confirm   Esc: cancel")
        if sh > 2:
            try:
                stdscr.addstr(sh - 2, 2, hint[: sw - 3], curses.color_pair(colors.DIM))
            except curses.error:
                pass

        # Error message
        if self._error and sh > 1:
            try:
                stdscr.addstr(
                    sh - 1,
                    2,
                    self._error[: sw - 3],
                    curses.color_pair(colors.ERROR) | curses.A_BOLD,
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

    def _field_handle_key(self, idx: int, key: int) -> None:
        f = self.fields[idx]
        buf = self._field_bufs[idx]
        cursor = self._field_cursors[idx]
        scroll = self._field_scrolls[idx]
        sh, sw = self.stdscr.getmaxyx()
        field_w = max(sw - self.LABEL_W - 6, 10)
        int_only = isinstance(f, IntField)

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
            if int_only:
                # Accept digits and a leading minus sign only
                if ch.isdigit() or (ch == "-" and cursor == 0 and not buf):
                    buf.insert(cursor, ch)
                    cursor += 1
            else:
                buf.insert(cursor, ch)
                cursor += 1

        # Update horizontal scroll
        if cursor - scroll >= field_w:
            scroll = cursor - field_w + 1
        elif cursor < scroll:
            scroll = cursor

        self._field_bufs[idx] = buf
        self._field_cursors[idx] = cursor
        self._field_scrolls[idx] = scroll
        self._error = ""
        self._field_errors[idx] = ""

    def _run_list_editor(self, field_idx: int) -> list[str]:
        """Full-screen inline list editor for a ListField.
        Temporarily replaces the form until Esc is pressed.
        Returns the (possibly modified) list."""
        f = self.fields[field_idx]
        items = list(self._list_vals[field_idx])
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
                    curses.color_pair(colors.HEADER) | curses.A_BOLD,
                )
                stdscr.addstr(1, 0, "─" * sw, curses.color_pair(colors.BORDER))
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
                    stdscr.addstr(
                        start_y, 2, "(empty list)", curses.color_pair(colors.DIM)
                    )
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
                        curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD
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
                stdscr.addstr(
                    sh - 2, 2, footer[: sw - 3], curses.color_pair(colors.DIM)
                )
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
            elif key in (ord("\n"), ord("\r")) and items:  # Edit
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
        for i, f in enumerate(self.fields):
            if isinstance(f, SectionField):
                continue
            elif isinstance(f, BoolField):
                result[f.key] = self._bool_vals[i]
            elif isinstance(f, ChoiceField):
                result[f.key] = f.choices[self._choice_idxs[i]] if f.choices else ""
            elif isinstance(f, IntField):
                s = "".join(self._field_bufs[i]).strip()
                try:
                    result[f.key] = int(s) if s else 0
                except ValueError:
                    result[f.key] = s  # invalid; _validate will catch it
            elif isinstance(f, ListField):
                result[f.key] = list(self._list_vals[i])
            else:
                result[f.key] = "".join(self._field_bufs[i])
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
                    self._field_errors[i] = err
                    return err
                if f.min_val is not None and val < f.min_val:
                    err = f'"{f.label}" must be \u2265 {f.min_val}'
                    self._field_errors[i] = err
                    return err
                if f.max_val is not None and val > f.max_val:
                    err = f'"{f.label}" must be \u2264 {f.max_val}'
                    self._field_errors[i] = err
                    return err
            if f.validator:
                err = f.validator(data.get(f.key, ""))
                if err:
                    return err
        return ""
