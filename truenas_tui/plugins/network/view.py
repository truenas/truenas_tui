"""
Network sub-menu plugin (default mode).

Presents a select_dialog sub-menu that wraps the three network plugins:
  - NetworkInterfacePlugin  (interface DHCP, aliases, MTU, etc.)
  - NetworkSettingsPlugin   (hostname, domain, gateways, DNS)
  - StaticRoutesPlugin      (add/remove static routes)

The individual plugins remain available in legacy --menu mode via their
LEGACY_INDEX values (1, 2, 3).  In default mode they are hidden
(DEFAULT_HIDDEN=True) and reached only through this sub-menu.
"""

from truenas_tui.plugins.base import BasePlugin
from truenas_tui.plugins.network_interface.view import NetworkInterfacePlugin
from truenas_tui.plugins.network_settings.view import NetworkSettingsPlugin
from truenas_tui.plugins.static_routes.view import StaticRoutesPlugin
from truenas_tui.tui.dialogs import select_dialog

from .localization import TRANSLATE


class NetworkPlugin(BasePlugin):
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Network"
    DESCRIPTION = (
        "Configure networking for this TrueNAS system.\n\n"
        "  \u2022 Interface settings  \u2013 DHCP, IP aliases, MTU\n"
        "  \u2022 Network settings    \u2013 Hostname, domain, gateways, DNS\n"
        "  \u2022 Static routes       \u2013 Add and remove static routes\n\n"
        "Changes to interfaces require a commit step\n"
        "before they take effect."
    )

    def run(self, stdscr, session) -> None:
        dialog_x = getattr(session, "_tui_dialog_x", None)
        pane_top = getattr(session, "_tui_pane_top", None)
        dialog_y = None
        if pane_top is not None and dialog_x is not None:
            sh = stdscr.getmaxyx()[0]
            desc_lines = len(self.get_description().splitlines())
            dialog_y = pane_top + desc_lines + 2
            dialog_y = min(dialog_y, sh - 5)

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
            choice = select_dialog(
                stdscr,
                TRANSLATE("Network"),
                options,
                selected,
                y=dialog_y,
                x=dialog_x,
            )
            if choice is None:
                break
            selected = choice
            sub_plugins[choice].run(stdscr, session)
            stdscr.clear()
