import curses

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.plugins.legacy_reboot.view import RebootPlugin
from truenas_tui.plugins.legacy_shutdown.view import ShutdownPlugin
from truenas_tui.session import Session
from truenas_tui.tui.dialogs import select_dialog


class PowerControlPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    LABEL = "Reboot/Shutdown"
    DESCRIPTION = (
        "Reboot or shut down the TrueNAS system.\n\n"
        "  • Reboot   – restart the system\n"
        "  • Shutdown – power off the system\n\n"
        "You will be prompted for a reason and confirmation\n"
        "before any action is taken."
    )

    def run(self, stdscr: curses.window, session: Session) -> None:
        choice = select_dialog(
            stdscr,
            TRANSLATE("Power Control"),
            [TRANSLATE("Reboot"), TRANSLATE("Shutdown")],
        )
        if choice == 0:
            RebootPlugin().run(stdscr, session)
        elif choice == 1:
            ShutdownPlugin().run(stdscr, session)
