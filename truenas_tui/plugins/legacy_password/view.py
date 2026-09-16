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
"""

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import message_dialog, new_password_dialog, select_dialog


class PasswordPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"ACCOUNT_WRITE"})
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

    def run(self, stdscr, session) -> None:
        try:
            has_admin = session.call("user.has_local_administrator_set_up")
        except Exception:
            has_admin = True
        if has_admin:
            self._change_password(stdscr, session)
        else:
            self._setup_administrator(stdscr, session)

    def _change_password(self, stdscr, session) -> None:
        try:
            admins = session.call("privilege.local_administrators")
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
        password = new_password_dialog(stdscr, TRANSLATE("Change Password"), username)
        if password is None:
            return

        try:
            session.call("user.update", user["id"], {"password": password})
            session.call("auth.twofactor.update", {"enabled": False})
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
        password = new_password_dialog(
            stdscr, TRANSLATE("Set Up Administrator"), username
        )
        if password is None:
            return

        try:
            session.call("user.setup_local_administrator", username, password)
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE("Local administrator {u} set up successfully.").format(
                    u=username
                ),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
