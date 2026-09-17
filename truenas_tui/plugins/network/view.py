"""
Network sub-menu plugin (default mode).

Presents a select_dialog sub-menu that wraps the three network plugins:
  - NetworkInterfacePlugin  (interface DHCP, aliases, MTU, etc.)
  - NetworkSettingsPlugin   (hostname, domain, gateways, DNS)
  - StaticRoutesPlugin      (add/remove static routes)

The individual plugins are also items 1, 2 and 3 of the legacy --menu mode.
"""

import curses

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.plugins.network_interface.view import NetworkInterfacePlugin
from truenas_tui.plugins.network_settings.view import NetworkSettingsPlugin
from truenas_tui.plugins.static_routes.view import StaticRoutesPlugin
from truenas_tui.session import Session
from truenas_tui.tui.dialogs import select_dialog


class NetworkPlugin(BasePlugin):
    LABEL = "Network"
    DESCRIPTION = (
        "Configure networking for this TrueNAS system.\n\n"
        "  • Interface settings  – DHCP, IP aliases, MTU\n"
        "  • Network settings    – Hostname, domain, gateways, DNS\n"
        "  • Static routes       – Add and remove static routes\n\n"
        "Changes to interfaces require a commit step\n"
        "before they take effect."
    )

    def run(self, stdscr: curses.window, session: Session) -> None:
        sub_plugins = [
            NetworkInterfacePlugin(),
            NetworkSettingsPlugin(),
            StaticRoutesPlugin(),
        ]
        options = [
            TRANSLATE("Interface settings"),
            TRANSLATE("Network settings"),
            TRANSLATE("Static routes"),
        ]
        selected = 0
        while True:
            choice = select_dialog(stdscr, TRANSLATE("Network"), options, selected)
            if choice is None:
                break
            selected = choice
            sub_plugins[choice].run(stdscr, session)
            stdscr.clear()
