"""
Generic curses dialog helpers.

All dialogs are modal overlays drawn in the centre of the screen.
They save/restore the underlying screen content automatically.
"""
import curses
from . import colors, HardExit
from truenas_tui.localization import TRANSLATE


def _draw_box(win, title: str = '') -> None:
    win.box()
    if title:
        h, w = win.getmaxyx()
        label = f' {title} '
        x = max(1, (w - len(label)) // 2)
        try:
            win.addstr(0, x, label, curses.color_pair(colors.TITLE) | curses.A_BOLD)
        except curses.error:
            pass


def _center_win(stdscr, height: int, width: int):
    """Create a centered window overlay."""
    sh, sw = stdscr.getmaxyx()
    y = max(0, (sh - height) // 2)
    x = max(0, (sw - width) // 2)
    # Clamp to screen
    height = min(height, sh)
    width = min(width, sw)
    win = curses.newwin(height, width, y, x)
    return win


def _save_screen(stdscr):
    """Snapshot the screen state for later restoration.

    dupwin() is not available on all Python/curses builds (notably Python 3.13
    on some platforms).  Falls back to None; callers must handle None.
    """
    try:
        return stdscr.dupwin()
    except AttributeError:
        return None


def _restore_screen(stdscr, saved) -> None:
    """Restore the screen state captured by _save_screen()."""
    if saved is not None:
        stdscr.overlay(saved)
    else:
        stdscr.touchwin()
    stdscr.refresh()


def message_dialog(stdscr, title: str, message: str, ok_label: str = 'OK',
                   timeout_secs: int = 0) -> None:
    """Show a message box.  Returns when the user presses Enter/Space/Esc/q.

    timeout_secs: if > 0 the dialog auto-dismisses after that many seconds.
    Used for sensitive output (e.g. one-time passwords) that should not linger.
    """
    lines = message.splitlines()
    width = max(len(ok_label) + 6, max((len(l) for l in lines), default=0) + 4, len(title) + 4)
    width = min(width, stdscr.getmaxyx()[1] - 2)
    height = len(lines) + 5  # title border + lines + blank + button row + border

    saved = _save_screen(stdscr)
    win = _center_win(stdscr, height, width)
    _draw_box(win, title)

    inner_w = width - 2
    for i, line in enumerate(lines):
        try:
            win.addstr(1 + i, 1, line[:inner_w])
        except curses.error:
            pass

    btn_label = f'[ {TRANSLATE(ok_label)} ]'
    btn_x = max(1, (width - len(btn_label)) // 2)
    try:
        win.addstr(height - 2, btn_x, btn_label,
                   curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD)
    except curses.error:
        pass

    win.refresh()
    curses.curs_set(0)

    if timeout_secs > 0:
        win.timeout(1000)   # wake up every second to update countdown
        remaining = timeout_secs
        while remaining > 0:
            countdown = f'[ {ok_label} ({remaining}s) ]'
            cx = max(1, (width - len(countdown)) // 2)
            try:
                win.addstr(height - 2, 1, ' ' * (width - 2))
                win.addstr(height - 2, cx, countdown,
                           curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD)
            except curses.error:
                pass
            win.refresh()
            key = win.getch()
            if key == 4:
                raise HardExit()
            if key in (ord('\n'), ord('\r'), ord(' '), 27, ord('q'), ord('Q')):
                break
            if key == -1:   # timeout tick
                remaining -= 1
        win.timeout(-1)
    else:
        while True:
            key = win.getch()
            if key == 4:
                raise HardExit()
            if key in (ord('\n'), ord('\r'), ord(' '), 27, ord('q'), ord('Q')):
                break

    # Restore
    _restore_screen(stdscr, saved)
    curses.curs_set(1)


def confirm_dialog(stdscr, title: str, message: str,
                   yes_label: str = 'Yes', no_label: str = 'No') -> bool:
    """
    Show a Yes/No confirmation dialog.
    Returns True if user chose Yes, False otherwise.
    Left/Right arrows or y/n switch selection; Enter confirms.
    """
    lines = message.splitlines()
    btn_row = f'[ {yes_label} ]   [ {no_label} ]'
    width = max(len(btn_row) + 4,
                max((len(l) for l in lines), default=0) + 4,
                len(title) + 4)
    width = min(width, stdscr.getmaxyx()[1] - 2)
    height = len(lines) + 5

    saved = _save_screen(stdscr)
    win = _center_win(stdscr, height, width)
    _draw_box(win, title)

    inner_w = width - 2
    for i, line in enumerate(lines):
        try:
            win.addstr(1 + i, 1, line[:inner_w])
        except curses.error:
            pass

    choice = 0  # 0 = Yes, 1 = No
    curses.curs_set(0)

    while True:
        yes_attr = curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD if choice == 0 else curses.A_NORMAL
        no_attr  = curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD if choice == 1 else curses.A_NORMAL
        yes_btn = f'[ {TRANSLATE(yes_label)} ]'
        no_btn  = f'[ {TRANSLATE(no_label)} ]'
        combined = f'{yes_btn}   {no_btn}'
        bx = max(1, (width - len(combined)) // 2)
        try:
            win.addstr(height - 2, bx, yes_btn, yes_attr)
            win.addstr(height - 2, bx + len(yes_btn) + 3, no_btn, no_attr)
        except curses.error:
            pass
        win.refresh()

        key = win.getch()
        if key == 4:
            raise HardExit()
        if key in (curses.KEY_LEFT, curses.KEY_RIGHT, ord('\t')):
            choice = 1 - choice
        elif key in (ord('y'), ord('Y')):
            choice = 0
            break
        elif key in (ord('n'), ord('N'), 27):
            choice = 1
            break
        elif key in (ord('\n'), ord('\r')):
            break

    _restore_screen(stdscr, saved)
    curses.curs_set(1)
    return choice == 0


def input_dialog(stdscr, title: str, prompt: str,
                 default: str = '', secret: bool = False) -> str | None:
    """
    Single-line text input dialog.
    Returns the entered string or None if cancelled (Esc/Ctrl+D).

    When secret=True only printable ASCII (0x20–0x7e) is accepted, preventing
    latin-1 high-bytes from being silently embedded in passwords.
    """
    inner_w = min(60, stdscr.getmaxyx()[1] - 6)
    width = inner_w + 4
    height = 7
    prompt_lines = prompt.splitlines()
    height += len(prompt_lines) - 1

    saved = _save_screen(stdscr)
    win = _center_win(stdscr, height, width)
    _draw_box(win, title)

    for i, line in enumerate(prompt_lines):
        try:
            win.addstr(1 + i, 2, line[:inner_w])
        except curses.error:
            pass

    field_y = 1 + len(prompt_lines) + 1
    try:
        win.addstr(field_y, 1, ' ' * inner_w, curses.color_pair(colors.MENU_SELECTED))
    except curses.error:
        pass

    hint = TRANSLATE('Enter: confirm  Esc: cancel')
    try:
        win.addstr(height - 2, 2, hint[:inner_w],
                   curses.color_pair(colors.DIM))
    except curses.error:
        pass

    curses.curs_set(1)
    win.keypad(True)

    buf = list(default)
    cursor = len(buf)
    scroll = 0

    while True:
        # Draw field
        display = ('*' * len(buf)) if secret else ''.join(buf)
        visible = display[scroll:scroll + inner_w]
        try:
            win.addstr(field_y, 1, visible.ljust(inner_w),
                       curses.color_pair(colors.MENU_SELECTED))
            cx = 1 + (cursor - scroll)
            win.move(field_y, cx)
        except curses.error:
            pass
        win.refresh()

        key = win.getch()

        if key == 27:           # Esc – cancel
            result = None
            break
        elif key == 4:          # Ctrl+D – hard exit
            raise HardExit()
        elif key in (ord('\n'), ord('\r')):
            result = ''.join(buf)
            break
        elif key in (curses.KEY_BACKSPACE, 127, 8):
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
        elif key == curses.KEY_HOME or key == 1:   # Ctrl+A
            cursor = 0
        elif key == curses.KEY_END or key == 5:    # Ctrl+E
            cursor = len(buf)
        elif key == 21:         # Ctrl+U – clear
            buf = []
            cursor = 0
        elif secret and 32 <= key <= 126:
            # Secret fields: ASCII printable only (0x20–0x7e)
            buf.insert(cursor, chr(key))
            cursor += 1
        elif not secret and 32 <= key < 256:
            buf.insert(cursor, chr(key))
            cursor += 1

        # Update scroll
        if cursor - scroll >= inner_w:
            scroll = cursor - inner_w + 1
        elif cursor < scroll:
            scroll = cursor

    _restore_screen(stdscr, saved)
    return result


def select_dialog(stdscr, title: str, options: list[str],
                  selected: int = 0,
                  y: int | None = None, x: int | None = None) -> int | None:
    """
    Scrollable list selection dialog.
    Returns the chosen index or None if cancelled.

    If both y and x are provided the window is placed at that position
    (left-aligned in the right pane) instead of being centred on screen.
    """
    if not options:
        return None

    sh, sw = stdscr.getmaxyx()
    max_opt_w = max(len(o) for o in options)

    saved = _save_screen(stdscr)

    if y is not None and x is not None:
        width = min(max(max_opt_w + 4, len(title) + 4, 30), sw - x - 2)
        visible_rows = min(len(options), sh - y - 4)
        height = visible_rows + 4
        # Clamp so window stays on screen
        y = max(0, min(y, sh - height))
        x = max(0, min(x, sw - width))
        win = curses.newwin(height, width, y, x)
    else:
        width = min(max(max_opt_w + 4, len(title) + 4, 30), sw - 4)
        visible_rows = min(len(options), sh - 6)
        height = visible_rows + 4
        win = _center_win(stdscr, height, width)
    _draw_box(win, title)

    hint = TRANSLATE('↑↓ Navigate  Enter Select  Esc Cancel')
    try:
        win.addstr(height - 2, 2, hint[:width - 3], curses.color_pair(colors.DIM))
    except curses.error:
        pass

    curses.curs_set(0)
    win.keypad(True)

    current = selected
    scroll_top = 0

    while True:
        # Keep current visible
        if current < scroll_top:
            scroll_top = current
        elif current >= scroll_top + visible_rows:
            scroll_top = current - visible_rows + 1

        inner_w = width - 2
        for i in range(visible_rows):
            idx = scroll_top + i
            if idx >= len(options):
                break
            label = options[idx][:inner_w - 2]
            attr = curses.color_pair(colors.MENU_SELECTED) | curses.A_BOLD if idx == current else curses.A_NORMAL
            try:
                win.addstr(1 + i, 1, f' {label:<{inner_w - 2}} ', attr)
            except curses.error:
                pass
        win.refresh()

        key = win.getch()
        if key == 4:
            raise HardExit()
        if key == curses.KEY_UP:
            current = max(0, current - 1)
        elif key == curses.KEY_DOWN:
            current = min(len(options) - 1, current + 1)
        elif key in (ord('\n'), ord('\r')):
            result = current
            break
        elif key in (27, ord('q')):   # Esc / q
            result = None
            break
        elif ord('1') <= key <= ord('9'):
            idx = key - ord('1')
            if idx < len(options):
                result = idx
                break

    _restore_screen(stdscr, saved)
    curses.curs_set(1)
    return result
