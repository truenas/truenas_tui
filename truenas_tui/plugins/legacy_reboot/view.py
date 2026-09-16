"""
Reboot plugin.

Prompts for a reboot reason then calls system.reboot.

API:
  system.reboot {"reason": str}

Version notes:
  Consistent across all supported API versions.
"""

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import confirm_dialog, input_dialog, message_dialog

from .localization import TRANSLATE


class RebootPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    LEGACY_INDEX = 9
    LEGACY_ONLY = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Reboot"
    DESCRIPTION = (
        "Reboot the TrueNAS system.\n"
        "\n"
        "You will be prompted to enter a reason for the reboot\n"
        "before the system restarts.\n"
        "\n"
        "All active sessions and shares will be interrupted."
    )

    def run(self, stdscr, session) -> None:
        reason = input_dialog(
            stdscr,
            TRANSLATE("Reboot"),
            TRANSLATE(
                "Please enter the reason for the system reboot\n"
                "(leave blank to cancel):"
            ),
        )
        if reason is None or reason.strip() == "":
            return

        if not confirm_dialog(
            stdscr,
            TRANSLATE("Confirm Reboot"),
            TRANSLATE("Reboot the system?\n\nReason: {r}").format(r=reason.strip()),
            yes_label=TRANSLATE("Reboot"),
            no_label=TRANSLATE("Cancel"),
        ):
            return

        try:
            session.call(Method.SYSTEM_REBOOT, {"reason": reason.strip()})
            message_dialog(
                stdscr,
                TRANSLATE("Rebooting"),
                TRANSLATE("Reboot initiated. The system is shutting down."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
