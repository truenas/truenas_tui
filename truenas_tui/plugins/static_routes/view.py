"""
Static Routes plugin.

Shows a list of static routes. Supports add, edit, and delete.

API:
  staticroute.query                          → list routes
  staticroute.create {destination, gateway, description}
  staticroute.update <id> {destination, gateway, description}
  staticroute.delete <id>
"""

import curses

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import HardExit, format_error
from truenas_tui.tui import colors
from truenas_tui.tui.colors import pair
from truenas_tui.tui.dialogs import message_dialog, confirm_dialog
from truenas_tui.tui.forms import Form, FormField
from .localization import TRANSLATE


class StaticRoutesPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"NETWORK_INTERFACE_WRITE"})
    LEGACY_INDEX = 3
    DEFAULT_HIDDEN = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Configure static routes"
    DESCRIPTION = (
        "Manage static network routes.\n"
        "\n"
        "  • View existing static routes\n"
        "  • Add new routes (destination, gateway, description)\n"
        "  • Edit or delete existing routes\n"
        "\n"
        "Keys: Enter = Edit,  a = Add,  d = Delete,  q = Back"
    )

    def run(self, stdscr, session) -> None:
        selected = 0
        stdscr.keypad(True)
        curses.curs_set(0)

        while True:
            try:
                routes = session.call(Method.STATICROUTE_QUERY)
            except Exception as e:
                message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
                return

            self._draw_list(stdscr, routes, selected)
            key = stdscr.getch()

            if key == 4:
                raise HardExit()
            elif key in (27, ord("q")):
                return
            elif key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(max(len(routes) - 1, 0), selected + 1)
            elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
                if routes:
                    self._edit_route(stdscr, session, routes[selected])
            elif key == ord("a"):
                self._add_route(stdscr, session)
            elif key == ord("d"):
                if routes:
                    self._delete_route(stdscr, session, routes[selected])
                    selected = max(0, selected - 1)

    def _draw_list(self, stdscr, routes: list, selected: int) -> None:
        stdscr.erase()
        sh, sw = stdscr.getmaxyx()
        title = TRANSLATE("Static Routes")
        stdscr.addstr(
            0, 0, f" {title} ".center(sw), pair(colors.HEADER) | curses.A_BOLD
        )

        if not routes:
            try:
                stdscr.addstr(2, 4, TRANSLATE("No static routes configured."))
            except curses.error:
                pass
        else:
            # Header row
            hdr = f"  {'Destination':<22}  {'Gateway':<20}  Description"
            try:
                stdscr.addstr(1, 0, hdr[:sw], curses.A_BOLD)
            except curses.error:
                pass
            for i, route in enumerate(routes):
                row = 2 + i
                if row >= sh - 2:
                    break
                dest = (route.get("destination") or "")[:22]
                gw = (route.get("gateway") or "")[:20]
                desc = route.get("description") or ""
                line = f"  {dest:<22}  {gw:<20}  {desc}"
                attr = (
                    pair(colors.MENU_SELECTED) | curses.A_BOLD
                    if i == selected
                    else curses.A_NORMAL
                )
                try:
                    stdscr.addstr(row, 0, line[: sw - 1].ljust(sw - 1), attr)
                except curses.error:
                    pass

        hint = TRANSLATE("[↑↓] Navigate  [Enter] Edit  [a] Add  [d] Delete  [q] Back")
        try:
            stdscr.addstr(sh - 1, 0, hint[:sw], pair(colors.HEADER))
        except curses.error:
            pass
        stdscr.refresh()

    def _route_form(self, stdscr, title: str, route: dict) -> dict | None:
        fields = [
            FormField(
                "destination",
                TRANSLATE("Destination (CIDR)"),
                route.get("destination", ""),
            ),
            FormField("gateway", TRANSLATE("Gateway"), route.get("gateway", "")),
            FormField(
                "description", TRANSLATE("Description"), route.get("description", "")
            ),
        ]
        return Form(stdscr, title, fields).run()

    def _add_route(self, stdscr, session) -> None:
        result = self._route_form(stdscr, TRANSLATE("Add Static Route"), {})
        if result is None:
            return
        try:
            session.call(Method.STATICROUTE_CREATE, result)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _edit_route(self, stdscr, session, route: dict) -> None:
        result = self._route_form(stdscr, TRANSLATE("Edit Static Route"), route)
        if result is None:
            return
        try:
            session.call(Method.STATICROUTE_UPDATE, route["id"], result)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _delete_route(self, stdscr, session, route: dict) -> None:
        dest = route.get("destination", "?")
        if confirm_dialog(
            stdscr,
            TRANSLATE("Delete Route"),
            TRANSLATE("Delete static route {dest}?").format(dest=dest),
        ):
            try:
                session.call(Method.STATICROUTE_DELETE, route["id"])
            except Exception as e:
                message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
