"""
Local Administrator Password plugin.

Behaviour matches midcli:
  - If user.has_local_administrator_set_up is True:
      • Show list of local administrators to choose from
      • Change selected user's password via user.update
      • Disable 2FA via auth.twofactor.update
  - Otherwise (fresh install / no admin):
      • Prompt to set up 'admin' or 'root'
      • Use user.setup_local_administrator

API version notes:
  auth.twofactor.update is present in all supported API versions.
"""

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import input_dialog, message_dialog, select_dialog

from .localization import TRANSLATE

_MIN_PASSWORD_LEN = 8


class PasswordPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"ACCOUNT_WRITE"})
    LEGACY_INDEX = 4
    LEGACY_ONLY = True
    REFRESH_INTERVAL = 60  # re-check admin setup state every minute
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Change local administrator password"
    DESCRIPTION = (
        "Change the password for a local administrator account.\n"
        "\n"
        "If no local administrator has been configured yet, this\n"
        "option lets you set up an initial admin or root account.\n"
        "\n"
        "Note: changing a password will disable two-factor\n"
        "authentication for that account."
    )

    def _fetch_label(self, session) -> str:
        try:
            has_admin = session.call(Method.USER_HAS_LOCAL_ADMINISTRATOR_SET_UP)
        except Exception:
            has_admin = True
        return (
            TRANSLATE("Change local administrator password")
            if has_admin
            else TRANSLATE("Set up local administrator")
        )

    def run(self, stdscr, session) -> None:
        label = self.get_label(session)
        has_admin = label == TRANSLATE("Change local administrator password")

        if has_admin:
            self._change_password(stdscr, session)
        else:
            self._setup_administrator(stdscr, session)

        self.refresh(session)  # label may have changed after password setup

    def _change_password(self, stdscr, session) -> None:
        try:
            admins = session.call(Method.PRIVILEGE_LOCAL_ADMINISTRATORS)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        if not admins:
            message_dialog(
                stdscr, TRANSLATE("Error"), TRANSLATE("No local administrators found.")
            )
            return

        options = [a["username"] for a in admins]
        idx = select_dialog(stdscr, TRANSLATE("Select Administrator"), options)
        if idx is None:
            return

        user = admins[idx]
        username = user["username"]

        pw1 = input_dialog(
            stdscr,
            TRANSLATE("Change Password"),
            TRANSLATE("New password for {u}:").format(u=username),
            secret=True,
        )
        if pw1 is None or pw1 == "":
            return

        if len(pw1) < _MIN_PASSWORD_LEN:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("Password must be at least {n} characters.").format(
                    n=_MIN_PASSWORD_LEN
                ),
            )
            return

        pw2 = input_dialog(
            stdscr,
            TRANSLATE("Change Password"),
            TRANSLATE("Retype password for {u}:").format(u=username),
            secret=True,
        )
        if pw2 is None:
            return

        if pw1 != pw2:
            message_dialog(
                stdscr, TRANSLATE("Error"), TRANSLATE("Passwords do not match.")
            )
            return

        try:
            session.call(Method.USER_UPDATE, user["id"], {"password": pw1})
            session.call(Method.AUTH_TWOFACTOR_UPDATE, {"enabled": False})
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE(
                    "Password for {u} changed successfully.\n"
                    "Two-factor authentication has been disabled."
                ).format(u=username),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _setup_administrator(self, stdscr, session) -> None:
        options = [
            TRANSLATE("Administrative user (admin)  [recommended]"),
            TRANSLATE("Root user (not recommended)"),
        ]
        idx = select_dialog(stdscr, TRANSLATE("Web UI Authentication Method"), options)
        if idx is None:
            return

        username = "admin" if idx == 0 else "root"

        pw1 = input_dialog(
            stdscr,
            TRANSLATE("Set Up Administrator"),
            TRANSLATE("Password for {u}:").format(u=username),
            secret=True,
        )
        if pw1 is None or pw1 == "":
            return

        if len(pw1) < _MIN_PASSWORD_LEN:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("Password must be at least {n} characters.").format(
                    n=_MIN_PASSWORD_LEN
                ),
            )
            return

        pw2 = input_dialog(
            stdscr,
            TRANSLATE("Set Up Administrator"),
            TRANSLATE("Retype password for {u}:").format(u=username),
            secret=True,
        )
        if pw2 is None:
            return

        if pw1 != pw2:
            message_dialog(
                stdscr, TRANSLATE("Error"), TRANSLATE("Passwords do not match.")
            )
            return

        try:
            session.call(Method.USER_SETUP_LOCAL_ADMINISTRATOR, username, pw1)
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE("Local administrator {u} set up successfully.").format(
                    u=username
                ),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
