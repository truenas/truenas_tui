"""
My Account plugin (default mode).

Displays auth.me account information and provides:
  - Change own password (user.set_password)
  - Generate a one-time password (auth.generate_onetime_password)
  - Set up / renew two-factor authentication (user.renew_2fa_secret)
  - Disable two-factor authentication (user.unset_2fa_secret)

API:
  auth.me                              → current user details
  user.set_password {username,
                     new_password,
                     old_password?}    → null
  auth.generate_onetime_password
    {username}                         → otp string
  user.renew_2fa_secret
    username, {otp_digits, interval}   → updated user dict with provisioning_uri
  user.unset_2fa_secret username       → null
"""

import curses
import shutil
import subprocess
import textwrap
from urllib.parse import parse_qs, urlparse

from truenas_tui.localization import TRANSLATE
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.plugins.onetime_password.view import show_onetime_password
from truenas_tui.session import Session
from truenas_tui.tui import HardExit, colors, format_error
from truenas_tui.tui.colors import pair
from truenas_tui.tui.dialogs import (
    confirm_dialog,
    input_dialog,
    message_dialog,
    new_password_dialog,
)


def _find_qr_tool() -> str | None:
    """Return path to a terminal QR code tool, or None if unavailable."""
    for name in ("qr", "qrcode-terminal"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _render_qr(uri: str, tool_path: str) -> str | None:
    """Run QR tool and return its stdout, or None on failure.

    The URI is passed via stdin (not as a command-line argument) to avoid
    exposing the TOTP secret in ps/proc output.  Both ``qr`` and
    ``qrcode-terminal`` read from stdin when invoked with no positional arg.
    """
    try:
        result = subprocess.run(
            [tool_path],
            input=uri,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except Exception:
        pass
    return None


def _extract_secret(uri: str) -> str:
    """Extract base32 secret from an otpauth:// URI."""
    try:
        return parse_qs(urlparse(uri).query).get("secret", [""])[0]
    except Exception:
        return ""


class MyAccountPlugin(BasePlugin):
    LABEL = "My account"
    DESCRIPTION = (
        "View your account information and manage credentials.\n\n"
        "  • View username, UID, roles, and 2FA status\n"
        "  • Change your password\n"
        "  • Generate a one-time password for single-use login\n"
        "  • Set up or renew two-factor authentication\n\n"
        "Password changes take effect immediately.\n"
        "One-time passwords expire after a single login."
    )

    def run(self, stdscr: curses.window, session: Session) -> None:
        try:
            me = session.call("auth.me")
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        username = me.get("pw_name", session.username)
        full_name = (me.get("pw_gecos") or "").strip()
        uid = str(me.get("pw_uid", ""))
        source = me.get("source", "LOCAL")
        is_local = me.get("local", source == "LOCAL")
        two_fa_config = me.get("two_factor_config", {})
        two_fa_configured = two_fa_config.get("secret_configured", False)
        roles = sorted(me.get("privilege", {}).get("roles", []))
        # READONLY_ADMIN implies every *_READ role; suppress them to avoid clutter
        if "READONLY_ADMIN" in roles:
            kept = []
            for r in roles:
                if not r.endswith("_READ"):
                    kept.append(r)
            roles = kept
        roles_str = ", ".join(roles) if roles else TRANSLATE("(none)")

        info_rows: list[tuple[str, str]] = [("Username", username)]
        if full_name:
            info_rows.append(("Full name", full_name))
        info_rows.extend(
            [
                ("UID", uid),
                ("Source", source),
                (
                    "2FA",
                    TRANSLATE("Enabled")
                    if two_fa_configured
                    else TRANSLATE("Disabled"),
                ),
                ("Roles", roles_str),
            ]
        )

        qr_tool = _find_qr_tool()
        actions: list[tuple[str, bool]] = [
            (TRANSLATE("Change password"), is_local),
            (TRANSLATE("Generate one-time password"), True),
        ]
        if not two_fa_configured:
            actions.append(
                (TRANSLATE("Set up two-factor authentication"), qr_tool is not None)
            )
        else:
            actions.append((TRANSLATE("Renew two-factor secret"), qr_tool is not None))
            actions.append((TRANSLATE("Disable two-factor authentication"), True))

        selected = 0
        stdscr.keypad(True)
        stdscr.timeout(-1)

        while True:
            self._draw(stdscr, username, info_rows, actions, selected)
            key = stdscr.getch()

            if key == 4:  # Ctrl+D
                raise HardExit()
            elif key in (27, ord("q"), ord("Q")):  # Esc / q – back
                break
            elif key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(len(actions) - 1, selected + 1)
            elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
                _, enabled = actions[selected]
                if not enabled:
                    message_dialog(
                        stdscr,
                        TRANSLATE("Unavailable"),
                        TRANSLATE(
                            "No terminal QR code tool was found on this system.\n\n"
                            'Install "qr" or "qrcode-terminal" to use this feature.'
                        ),
                    )
                elif selected == 0:
                    self._change_password(stdscr, session, username, is_local)
                elif selected == 1:
                    show_onetime_password(stdscr, session, username)
                elif selected == 2:
                    self._setup_2fa(
                        stdscr, session, username, two_fa_configured, qr_tool
                    )
                elif selected == 3:
                    self._disable_2fa(stdscr, session, username)
                stdscr.clear()

    def _draw(
        self,
        stdscr: curses.window,
        username: str,
        info_rows: list[tuple[str, str]],
        actions: list[tuple[str, bool]],
        selected: int,
    ) -> None:
        try:
            sh, sw = stdscr.getmaxyx()
            stdscr.erase()

            # Header
            title = TRANSLATE(" My Account – {u} ").format(u=username)
            try:
                stdscr.addstr(
                    0, 0, title[:sw].ljust(sw), pair(colors.HEADER) | curses.A_BOLD
                )
            except curses.error:
                pass

            # Account info
            label_w = 0
            for k, _ in info_rows:
                if len(k) > label_w:
                    label_w = len(k)
            val_x = 2 + label_w + 2
            val_w = max(1, sw - val_x - 1)
            row = 2
            for key, val in info_rows:
                if row >= sh - 5:
                    break
                lines = textwrap.wrap(val, val_w, break_long_words=False) or [""]
                for i, line in enumerate(lines):
                    if row >= sh - 5:
                        break
                    try:
                        if i == 0:
                            stdscr.addstr(row, 2, f"{key:<{label_w}}", curses.A_BOLD)
                        stdscr.addstr(row, val_x, line)
                    except curses.error:
                        pass
                    row += 1

            # Divider
            row += 1
            if row < sh - 4:
                try:
                    stdscr.addstr(row, 0, "─" * (sw - 1))
                except curses.error:
                    pass
                row += 1

            # Actions heading
            if row < sh - 3:
                try:
                    stdscr.addstr(row, 2, TRANSLATE("Actions:"), curses.A_BOLD)
                except curses.error:
                    pass
                row += 1

            # Action items
            for i, (action, enabled) in enumerate(actions):
                if row >= sh - 2:
                    break
                suffix = TRANSLATE(" (no QR tool found)") if not enabled else ""
                display = action + suffix
                if not enabled:
                    attr = curses.A_DIM | (curses.A_REVERSE if i == selected else 0)
                elif i == selected:
                    attr = pair(colors.MENU_SELECTED) | curses.A_BOLD
                else:
                    attr = pair(colors.MENU_NORMAL)
                try:
                    stdscr.addstr(row, 2, ("  " + display)[: sw - 3], attr)
                    if i == selected:
                        stdscr.addstr(row, 2, ">", attr)
                except curses.error:
                    pass
                row += 1

            # Footer
            footer = " ↑↓ Navigate   Enter Select   Esc/q Back   ^D Quit"
            try:
                stdscr.addstr(sh - 1, 0, footer[:sw].ljust(sw), pair(colors.HEADER))
            except curses.error:
                pass

            stdscr.noutrefresh()
            curses.doupdate()
        except curses.error:
            pass

    def _change_password(
        self, stdscr: curses.window, session: Session, username: str, is_local: bool
    ) -> None:
        if not is_local:
            message_dialog(
                stdscr,
                TRANSLATE("Cannot Change Password"),
                TRANSLATE(
                    "Password changes are only supported for local accounts.\n"
                    "This account is managed by an external directory service."
                ),
            )
            return

        old_pw = None
        if "FULL_ADMIN" not in session.roles:
            old_pw = input_dialog(
                stdscr,
                TRANSLATE("Change Password"),
                TRANSLATE("Current password:"),
                secret=True,
            )
            if old_pw is None:
                return

        new_pw = new_password_dialog(stdscr, TRANSLATE("Change Password"), username)
        if new_pw is None:
            return

        params = {"username": username, "new_password": new_pw}
        if old_pw is not None:
            params["old_password"] = old_pw

        try:
            session.call("user.set_password", params)
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE("Password changed successfully."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _setup_2fa(
        self,
        stdscr: curses.window,
        session: Session,
        username: str,
        already_configured: bool,
        qr_tool: str | None,
    ) -> None:
        """Set up (or renew) TOTP 2FA for the current user."""
        if already_configured:
            confirmed = confirm_dialog(
                stdscr,
                TRANSLATE("Renew 2FA Secret"),
                TRANSLATE(
                    "Generating a new 2FA secret will invalidate your current\n"
                    "authenticator app configuration. Continue?"
                ),
            )
            if not confirmed:
                return

        try:
            result = session.call(
                "user.renew_2fa_secret",
                username,
                {"otp_digits": 6, "interval": 30},
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        uri = (result or {}).get("two_factor_config", {}).get("provisioning_uri", "")
        if not uri:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("No provisioning URI returned from server."),
            )
            return

        self._show_2fa_setup(stdscr, uri, qr_tool)

    def _disable_2fa(
        self, stdscr: curses.window, session: Session, username: str
    ) -> None:
        """Disable TOTP 2FA for the current user."""
        confirmed = confirm_dialog(
            stdscr,
            TRANSLATE("Disable Two-Factor Authentication"),
            TRANSLATE(
                "Disable two-factor authentication for {u}?\n"
                "You will no longer need an OTP to log in."
            ).format(u=username),
        )
        if not confirmed:
            return

        try:
            session.call("user.unset_2fa_secret", username)
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE("Two-factor authentication has been disabled."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _show_2fa_setup(
        self, stdscr: curses.window, uri: str, qr_tool: str | None
    ) -> None:
        """Full-screen 2FA provisioning display. Blocks until user presses Enter."""
        secret = _extract_secret(uri)
        qr_output = _render_qr(uri, qr_tool) if qr_tool else None

        try:
            sh, sw = stdscr.getmaxyx()
            stdscr.erase()

            # Header
            title = TRANSLATE(" Two-Factor Authentication Setup ")
            try:
                stdscr.addstr(
                    0, 0, title[:sw].ljust(sw), pair(colors.HEADER) | curses.A_BOLD
                )
            except curses.error:
                pass

            row = 2
            for line in [
                TRANSLATE("IMPORTANT: Scan this QR code with your authenticator app"),
                TRANSLATE(
                    "(Google Authenticator, Authy, etc.) before navigating away."
                ),
                TRANSLATE("Without it you may be locked out of this system."),
            ]:
                if row < sh - 3:
                    try:
                        stdscr.addstr(row, 1, line[: sw - 2])
                    except curses.error:
                        pass
                    row += 1

            row += 1

            # QR code output or fallback URI
            if qr_output:
                for line in qr_output.splitlines():
                    if row >= sh - 3:
                        break
                    try:
                        stdscr.addstr(row, 1, line[: sw - 2])
                    except curses.error:
                        pass
                    row += 1
            else:
                if row < sh - 3:
                    try:
                        stdscr.addstr(row, 1, uri[: sw - 2])
                    except curses.error:
                        pass
                    row += 1

            row += 1

            # Secret key for manual entry
            if secret and row < sh - 2:
                secret_line = TRANSLATE("Secret key: {s}  (for manual entry)").format(
                    s=secret
                )
                try:
                    stdscr.addstr(row, 1, secret_line[: sw - 2], curses.A_BOLD)
                except curses.error:
                    pass

            # Footer
            footer = TRANSLATE(" Press Enter to continue")
            try:
                stdscr.addstr(sh - 1, 0, footer[:sw].ljust(sw), pair(colors.HEADER))
            except curses.error:
                pass

            stdscr.noutrefresh()
            curses.doupdate()
        except curses.error:
            pass

        # Wait for Enter / Esc / ^D
        stdscr.keypad(True)
        while True:
            key = stdscr.getch()
            if key == 4:
                raise HardExit()
            if key in (ord("\n"), ord("\r"), curses.KEY_ENTER, 27, ord("q"), ord("Q")):
                break
