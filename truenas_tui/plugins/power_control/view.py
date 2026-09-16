from truenas_tui.plugins.base import BasePlugin
from truenas_tui.plugins.legacy_reboot.view import RebootPlugin
from truenas_tui.plugins.legacy_shutdown.view import ShutdownPlugin
from truenas_tui.tui.dialogs import select_dialog

from .localization import TRANSLATE


class PowerControlPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Reboot/Shutdown"
    DESCRIPTION = (
        "Reboot or shut down the TrueNAS system.\n\n"
        "  \u2022 Reboot   \u2013 restart the system\n"
        "  \u2022 Shutdown \u2013 power off the system\n\n"
        "You will be prompted for a reason and confirmation\n"
        "before any action is taken."
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

        choice = select_dialog(
            stdscr,
            TRANSLATE("Power Control"),
            [TRANSLATE("Reboot"), TRANSLATE("Shutdown")],
            y=dialog_y,
            x=dialog_x,
        )
        if choice == 0:
            RebootPlugin().run(stdscr, session)
        elif choice == 1:
            ShutdownPlugin().run(stdscr, session)
