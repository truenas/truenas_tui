"""
Shutdown plugin.

Prompts for a shutdown reason then calls system.shutdown.

API:
  system.shutdown {"reason": str}

Version notes:
  Consistent across all supported API versions.
"""

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import message_dialog, confirm_dialog, input_dialog
from .localization import TRANSLATE


class ShutdownPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    LEGACY_INDEX = 10
    LEGACY_ONLY = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Shutdown"
    DESCRIPTION = (
        "Shut down the TrueNAS system.\n"
        "\n"
        "You will be prompted to enter a reason for the shutdown\n"
        "before the system powers off.\n"
        "\n"
        "All active sessions and shares will be interrupted."
    )

    def run(self, stdscr, session) -> None:
        reason = input_dialog(
            stdscr,
            TRANSLATE("Shutdown"),
            TRANSLATE(
                "Please enter the reason for the system shutdown\n"
                "(leave blank to cancel):"
            ),
        )
        if reason is None or reason.strip() == "":
            return

        if not confirm_dialog(
            stdscr,
            TRANSLATE("Confirm Shutdown"),
            TRANSLATE("Shut down the system?\n\nReason: {r}").format(r=reason.strip()),
            yes_label=TRANSLATE("Shutdown"),
            no_label=TRANSLATE("Cancel"),
        ):
            return

        try:
            session.call(Method.SYSTEM_SHUTDOWN, {"reason": reason.strip()})
            message_dialog(
                stdscr,
                TRANSLATE("Shutting Down"),
                TRANSLATE("Shutdown initiated. The system is powering off."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
