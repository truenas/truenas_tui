"""
One-Time Password plugin.

Generates a one-time password for the currently authenticated user.
show_onetime_password() is shared with the My Account plugin.

API:
  auth.generate_onetime_password    → {username: str} → otp string
"""

import curses

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.session import Session
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import message_dialog

_OTP_DISPLAY_TIMEOUT = 30  # seconds before the OTP dialog auto-dismisses


def show_onetime_password(
    stdscr: curses.window, session: Session, username: str
) -> None:
    """Generate a one-time password for username and show it briefly."""
    try:
        otp = session.call("auth.generate_onetime_password", {"username": username})
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


class OnetimePasswordPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"ACCOUNT_WRITE"})
    LABEL = "Create one-time password"
    DESCRIPTION = (
        "Generate a single-use temporary password for the\n"
        "currently authenticated user.\n"
        "\n"
        "The one-time password can be used to log in once\n"
        "and is invalidated immediately after use."
    )

    def get_label(self, session: Session) -> str:
        return TRANSLATE('Create one-time password for "{u}"').format(
            u=session.username
        )

    def run(self, stdscr: curses.window, session: Session) -> None:
        show_onetime_password(stdscr, session, session.username)
