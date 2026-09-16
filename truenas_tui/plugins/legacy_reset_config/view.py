"""
Reset Configuration plugin.

Resets TrueNAS configuration to factory defaults after double confirmation.

API:
  system.config.reset   → resets config (no args required in current versions)

Version notes:
  v25.04+: system.config.reset takes no arguments.
"""

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import confirm_dialog, input_dialog, message_dialog


class ResetConfigPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"FULL_ADMIN"})
    LABEL = "Reset configuration to defaults"
    DESCRIPTION = (
        "Erase all TrueNAS configuration and reset to factory\n"
        "defaults.\n"
        "\n"
        "WARNING: This is irreversible. All settings including\n"
        "network configuration, shares, users, and storage pools\n"
        "will be erased.\n"
        "\n"
        "You will be prompted to confirm twice before proceeding."
    )

    def run(self, stdscr, session) -> None:
        # First confirmation
        if not confirm_dialog(
            stdscr,
            TRANSLATE("Reset Configuration"),
            TRANSLATE(
                "This will ERASE all configuration and reset to defaults.\n"
                "Are you absolutely sure?"
            ),
            yes_label=TRANSLATE("Yes, reset"),
            no_label=TRANSLATE("Cancel"),
        ):
            return

        # Second confirmation – type "RESET" to proceed
        typed = input_dialog(
            stdscr,
            TRANSLATE("Confirm Reset"),
            TRANSLATE("Type RESET to confirm (case-sensitive):"),
        )
        if typed != "RESET":
            message_dialog(
                stdscr,
                TRANSLATE("Cancelled"),
                TRANSLATE("Configuration reset cancelled."),
            )
            return

        try:
            session.call("system.config.reset")
            message_dialog(
                stdscr,
                TRANSLATE("Reset"),
                TRANSLATE(
                    "Configuration reset initiated.\n"
                    "The system will reboot with default settings."
                ),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
