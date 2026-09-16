"""
One-Time Password plugin.

Generates a one-time password for the currently authenticated user.

API:
  auth.me                           → get current username
  auth.generate_onetime_password    → {username: str} → otp string
"""

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import message_dialog

from .localization import TRANSLATE

_OTP_DISPLAY_TIMEOUT = 30  # seconds before the OTP dialog auto-dismisses


class OnetimePasswordPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"ACCOUNT_WRITE"})
    LEGACY_INDEX = 5
    LEGACY_ONLY = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Create one-time password"
    DESCRIPTION = (
        "Generate a single-use temporary password for the\n"
        "currently authenticated user.\n"
        "\n"
        "The one-time password can be used to log in once\n"
        "and is invalidated immediately after use."
    )

    def get_label(self, session) -> str:
        username = session.username
        return TRANSLATE('Create one-time password for "{u}"').format(u=username)

    def run(self, stdscr, session) -> None:
        username = session.username
        try:
            otp = session.call(
                Method.AUTH_GENERATE_ONETIME_PASSWORD, {"username": username}
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        message_dialog(
            stdscr,
            TRANSLATE("One-Time Password"),
            TRANSLATE(
                'One-time password for "{u}":\n\n  {otp}\n\n'
                "This password can only be used once.\n"
                "Dialog closes automatically after {t} seconds."
            ).format(u=username, otp=otp, t=_OTP_DISPLAY_TIMEOUT),
            timeout_secs=_OTP_DISPLAY_TIMEOUT,
        )
