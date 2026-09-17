"""
Reboot plugin.

Prompts for a reboot reason, confirms, then calls system.reboot.
ShutdownPlugin reuses the same flow with its own strings and method.
"""

import curses

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.session import Session
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import confirm_dialog, input_dialog, message_dialog


class RebootPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    LABEL = "Reboot"
    DESCRIPTION = (
        "Reboot the TrueNAS system.\n"
        "\n"
        "You will be prompted to enter a reason for the reboot\n"
        "before the system restarts.\n"
        "\n"
        "All active sessions and shares will be interrupted."
    )
    _METHOD = "system.reboot"

    def _texts(self) -> tuple[str, str, str, str, str]:
        """Reason prompt, confirm title, confirm body, done title, done body."""
        return (
            TRANSLATE(
                "Please enter the reason for the system reboot\n"
                "(leave blank to cancel):"
            ),
            TRANSLATE("Confirm Reboot"),
            TRANSLATE("Reboot the system?\n\nReason: {r}"),
            TRANSLATE("Rebooting"),
            TRANSLATE("Reboot initiated. The system is shutting down."),
        )

    def run(self, stdscr: curses.window, session: Session) -> None:
        prompt, confirm_title, confirm_body, done_title, done_body = self._texts()
        label = TRANSLATE(self.LABEL)

        reason = input_dialog(stdscr, label, prompt)
        if reason is None or reason.strip() == "":
            return
        reason = reason.strip()

        if not confirm_dialog(
            stdscr,
            confirm_title,
            confirm_body.format(r=reason),
            yes_label=label,
            no_label=TRANSLATE("Cancel"),
        ):
            return

        try:
            session.call(self._METHOD, {"reason": reason})
            message_dialog(stdscr, done_title, done_body)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
