"""
Two-pane main TUI view.

Layout (legacy --menu mode)::

  ┌─ TrueNAS 25.10.0 - bobnas (192.168.1.108)  User: admin [READONLY_ADMIN] ─┐
  │ Menu                         │ Description / active plugin               │
  │ ─────────────────────────── │ ──────────────────────────────────────── │
  │ >  1. Network interfaces     │                                           │
  │    2. Network settings       │  <right pane – plugin desc or sysinfo>    │
  │    ...                       │                                           │
  │   10. Shutdown               │                                           │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ Enter an option from 1-10:  ↑↓ Navigate  Enter Select  ^D/q Quit        │
  └──────────────────────────────────────────────────────────────────────────┘

Layout (default mode)::

  ┌─ TrueNAS 25.10.0 - bobnas (192.168.1.108)  User: admin [READONLY_ADMIN] ─┐
  │ Menu                         │ Description / active plugin               │
  │ ─────────────────────────── │ ──────────────────────────────────────── │
  │ >    Network interfaces      │                                           │
  │      Network settings        │  <right pane – plugin desc or sysinfo>    │
  │      ...                     │                                           │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ ↑↓ Navigate   Enter Select   r Refresh   Esc Info   ^D/q Quit           │
  └──────────────────────────────────────────────────────────────────────────┘

Right-pane modes:
  Info mode  (startup, or Esc from menu) – system.info table, auto-refreshes
             every 10 s.  Any navigation key switches to description mode.
  Desc mode  – shows the selected plugin's description.

Keyboard shortcuts:
  Legacy mode only:
    1–9     – activate the menu item with that number
  Default mode only:
    s       – open the TUI settings form
  Both modes:
    ↑ / ↓   – move selection
    Enter   – activate selected item
    r       – refresh system info
    Esc     – return to system info view
    Ctrl+D / q – quit
"""

import curses
import signal
import time

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.tui_settings.view import TuiSettingsPlugin

from . import HardExit, colors, format_error
from .colors import pair
from .dialogs import message_dialog

_INFO_REFRESH_SECS = 10
_MENU_MIN = 24
_MENU_MAX_FRAC = 0.45  # never wider than 45 % of the terminal


def _fmt_bytes(n: int) -> str:
    return f"{n / (1024**3):.1f} GiB"


def _fmt_load(loadavg: list) -> str:
    return "  ".join(f"{v:.2f}" for v in loadavg[:3])


class MainView:
    def __init__(self, stdscr, session, plugins: list, menu_mode: bool = False):
        self.stdscr = stdscr
        self.session = session
        self.plugins = plugins
        self.selected = 0
        self._menu_mode = menu_mode
        self._info_mode = session.tui_prefs.startup_view == "sysinfo"
        self._info_next_refresh = time.monotonic() + _INFO_REFRESH_SECS
        self._resize_pending = False

        signal.signal(signal.SIGWINCH, self._handle_resize)

    def run(self) -> None:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.stdscr.timeout(1000)  # 1-second tick for info refresh

        while True:
            self._draw()
            key = self.stdscr.getch()

            if key == -1:  # timeout tick
                if self._resize_pending:
                    self._resize_pending = False
                    try:
                        curses.endwin()
                        self.stdscr.refresh()
                    except curses.error:
                        pass
                if self._info_mode and time.monotonic() >= self._info_next_refresh:
                    self._refresh_info()
            elif key == 4:  # Ctrl+D – hard exit
                raise HardExit()
            elif key in (ord("q"), ord("Q")):  # quit
                break
            elif key == 27:  # Esc – back to info view
                self._info_mode = True
                self._info_next_refresh = time.monotonic() + _INFO_REFRESH_SECS
            elif key == curses.KEY_UP:
                self._info_mode = False
                self.selected = max(0, self.selected - 1)
            elif key == curses.KEY_DOWN:
                self._info_mode = False
                self.selected = min(len(self.plugins) - 1, self.selected + 1)
            elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
                self._info_mode = False
                if self.plugins:
                    self._run_plugin(self.plugins[self.selected])
            elif key in (ord("r"), ord("R")):
                self._refresh_info()
            elif self._menu_mode and ord("1") <= key <= ord("9"):
                idx = key - ord("1")
                if idx < len(self.plugins):
                    self._info_mode = False
                    self.selected = idx
                    self._run_plugin(self.plugins[idx])
            elif key in (ord("s"), ord("S")) and not self._menu_mode:
                self._run_plugin(TuiSettingsPlugin())

    def _refresh_info(self) -> None:
        try:
            self.session.system_info = self.session.call("system.info")
        except Exception:
            pass
        self._info_next_refresh = time.monotonic() + _INFO_REFRESH_SECS

    def _run_plugin(self, plugin) -> None:
        curses.curs_set(1)
        try:
            plugin.run(self.stdscr, self.session)
        except Exception as e:
            message_dialog(self.stdscr, "Error", format_error(e))
        finally:
            curses.curs_set(0)
            self.stdscr.clear()

    def _draw(self) -> None:
        try:
            sh, sw = self.stdscr.getmaxyx()
            self.stdscr.erase()
            self._draw_header(sh, sw)
            self._draw_panes(sh, sw)
            self._draw_footer(sh, sw)
            self.stdscr.noutrefresh()
            curses.doupdate()
        except curses.error:
            pass

    def _draw_header(self, sh: int, sw: int) -> None:
        s = self.session
        hostname = s.hostname
        version = s.version
        server = s.config.server or "local"
        username = s.username
        role = s.role_label

        left = f" TrueNAS {version} – {hostname} ({server})"
        right = f"User: {username} [{role}] "
        gap = sw - len(left) - len(right)
        if gap < 1:
            gap = 1
        header = f"{left}{' ' * gap}{right}"

        try:
            self.stdscr.addstr(0, 0, header[:sw], pair(colors.HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        if username == "root":
            warn = " *** " + TRANSLATE("WARNING: You are logged in as root!") + " ***"
            try:
                self.stdscr.addstr(
                    1, 0, warn[:sw].center(sw), pair(colors.WARNING) | curses.A_BOLD
                )
            except curses.error:
                pass

    def _divider_x(self, sw: int) -> int:
        max_label = max(
            (5 + len(p.get_label(self.session)) for p in self.plugins),
            default=_MENU_MIN,
        )
        return min(max(max_label + 1, _MENU_MIN), int(sw * _MENU_MAX_FRAC))

    def _draw_panes(self, sh: int, sw: int) -> None:
        header_rows = 2 if self.session.username == "root" else 1
        footer_rows = 1
        pane_top = header_rows
        pane_bottom = sh - footer_rows - 1

        if pane_bottom <= pane_top:
            return

        divider_x = self._divider_x(sw)
        for row in range(pane_top, pane_bottom + 1):
            try:
                self.stdscr.addch(row, divider_x, curses.ACS_VLINE, pair(colors.BORDER))
            except curses.error:
                pass

        self._draw_menu(pane_top, pane_bottom, divider_x)
        if self._info_mode:
            self._draw_info(pane_top, pane_bottom, divider_x, sw)
        else:
            self._draw_content(pane_top, pane_bottom, divider_x, sw)

    def _draw_menu(self, top: int, bottom: int, width: int) -> None:
        visible_rows = bottom - top
        scroll = max(0, self.selected - visible_rows + 1)

        for i, plugin in enumerate(self.plugins):
            row = top + (i - scroll)
            if row < top or row > bottom:
                continue

            label = plugin.get_label(self.session)
            prefix = f" {i + 1:>2}. " if self._menu_mode else "     "
            line = (prefix + label)[: width - 1].ljust(width - 1)

            attr = (
                pair(colors.MENU_SELECTED) | curses.A_BOLD
                if i == self.selected
                else pair(colors.MENU_NORMAL)
            )
            try:
                self.stdscr.addstr(row, 0, line, attr)
                if i == self.selected:
                    self.stdscr.addstr(row, 0, ">", attr | curses.A_BOLD)
            except curses.error:
                pass

    def _draw_content(self, top: int, bottom: int, left: int, sw: int) -> None:
        if not self.plugins:
            return
        plugin = self.plugins[self.selected]
        desc = plugin.get_description()
        lines = desc.splitlines()
        content_w = sw - left - 2
        col = left + 2

        title = f" {plugin.get_label(self.session)} "
        try:
            self.stdscr.addstr(
                top, left + 1, title[:content_w], pair(colors.TITLE) | curses.A_BOLD
            )
        except curses.error:
            pass

        for i, line in enumerate(lines):
            row = top + 1 + i
            if row > bottom:
                break
            try:
                self.stdscr.addstr(row, col, line[:content_w])
            except curses.error:
                pass

        # Privilege indicator at the bottom of the pane
        if plugin.can_write(self.session.roles):
            access_text = TRANSLATE("Access: Read/Write")
            access_attr = pair(colors.SUCCESS) | curses.A_BOLD
        else:
            access_text = TRANSLATE("Access: Read-only")
            access_attr = pair(colors.WARNING) | curses.A_BOLD
        try:
            self.stdscr.addstr(bottom, col, access_text[:content_w], access_attr)
        except curses.error:
            pass

    def _draw_info(self, top: int, bottom: int, left: int, sw: int) -> None:
        """Draw system.info as a table in the right content pane."""
        si = self.session.system_info
        content_w = sw - left - 2
        col = left + 2

        title = f" {TRANSLATE('System Information')} "
        try:
            self.stdscr.addstr(
                top, left + 1, title[:content_w], pair(colors.TITLE) | curses.A_BOLD
            )
        except curses.error:
            pass

        rows = [
            (TRANSLATE("Version"), si.get("version", "")),
            (TRANSLATE("Hostname"), si.get("hostname", "")),
            ("", ""),
            (TRANSLATE("Product"), si.get("system_product") or ""),
            (TRANSLATE("Serial"), si.get("system_serial") or ""),
            (TRANSLATE("Manufacturer"), si.get("system_manufacturer") or ""),
            ("", ""),
            (
                TRANSLATE("CPU"),
                f"{si.get('model', '')}  "
                f"({si.get('physical_cores', '')} cores / "
                f"{si.get('cores', '')} threads)",
            ),
            (
                TRANSLATE("Memory"),
                (_fmt_bytes(si["physmem"]) + ("  ECC" if si.get("ecc_memory") else ""))
                if si.get("physmem")
                else "",
            ),
            ("", ""),
            (TRANSLATE("Uptime"), si.get("uptime", "")),
            (
                TRANSLATE("Load Average"),
                _fmt_load(si["loadavg"]) if si.get("loadavg") else "",
            ),
            (TRANSLATE("Timezone"), si.get("timezone", "")),
        ]

        label_w = max((len(r[0]) for r in rows), default=0) + 1

        row_y = top + 1
        for label, value in rows:
            if row_y > bottom:
                break
            if not label:
                row_y += 1
                continue
            try:
                self.stdscr.addstr(row_y, col, f"{label:<{label_w}}", curses.A_BOLD)
                self.stdscr.addstr(
                    row_y, col + label_w + 1, value[: content_w - label_w - 1]
                )
            except curses.error:
                pass
            row_y += 1

        # Refresh hint at bottom of pane
        hint = TRANSLATE("Auto-refreshes every {n}s  [r] force refresh").format(
            n=_INFO_REFRESH_SECS
        )
        if row_y + 1 <= bottom:
            try:
                self.stdscr.addstr(bottom, col, hint[:content_w], pair(colors.DIM))
            except curses.error:
                pass

    def _draw_footer(self, sh: int, sw: int) -> None:
        if self._menu_mode:
            prompt = f" Enter an option from 1-{len(self.plugins)}: "
            if self._info_mode:
                keys = "↑↓/Enter Navigate/Select   r Refresh   ^D/q Quit"
            else:
                keys = "↑↓ Navigate   Enter Select   r Refresh   Esc Info   ^D/q Quit"
            gap = sw - len(prompt) - len(keys)
            if gap < 1:
                gap = 1
            footer = f"{prompt}{' ' * gap}{keys} "
        else:
            if self._info_mode:
                keys = " ↑↓/Enter Navigate/Select   r Refresh   s Settings   ^D/q Quit"
            else:
                keys = " ↑↓ Navigate   Enter Select   r Refresh   s Settings   Esc Info   ^D/q Quit"
            footer = keys.ljust(sw)

        try:
            self.stdscr.addstr(sh - 1, 0, footer[:sw], pair(colors.HEADER))
        except curses.error:
            pass

    def _handle_resize(self, signum, frame) -> None:
        self._resize_pending = True
