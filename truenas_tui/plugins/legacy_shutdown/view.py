"""
Shutdown plugin.

Same flow as RebootPlugin with the shutdown strings and system.shutdown.
"""

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.legacy_reboot.view import RebootPlugin


class ShutdownPlugin(RebootPlugin):
    LABEL = "Shutdown"
    DESCRIPTION = (
        "Shut down the TrueNAS system.\n"
        "\n"
        "You will be prompted to enter a reason for the shutdown\n"
        "before the system powers off.\n"
        "\n"
        "All active sessions and shares will be interrupted."
    )
    _METHOD = "system.shutdown"

    def _texts(self) -> tuple[str, str, str, str, str]:
        return (
            TRANSLATE(
                "Please enter the reason for the system shutdown\n"
                "(leave blank to cancel):"
            ),
            TRANSLATE("Confirm Shutdown"),
            TRANSLATE("Shut down the system?\n\nReason: {r}"),
            TRANSLATE("Shutting Down"),
            TRANSLATE("Shutdown initiated. The system is powering off."),
        )
