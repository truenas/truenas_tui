"""
Group 2 – Interface Mapping: Password, OnetimePassword, and MyAccount plugins.

Strategy: patch dialog helpers at their import binding sites; use
RecordingMockSession (with .override() where needed) to assert correct
API calls.

Key flow for PasswordPlugin:
  get_label() → _fetch_label() → USER_HAS_LOCAL_ADMINISTRATOR_SET_UP
  True  → _change_password() → PRIVILEGE_LOCAL_ADMINISTRATORS + USER_UPDATE
  False → _setup_administrator() → USER_SETUP_LOCAL_ADMINISTRATOR
"""

import curses
from unittest.mock import patch

import pytest

from truenas_tui.api_methods import Method
from truenas_tui.plugins.legacy_password.view import PasswordPlugin
from truenas_tui.plugins.my_account.view import (
    MyAccountPlugin,
    _extract_secret,
    _find_qr_tool,
)
from truenas_tui.plugins.onetime_password.view import OnetimePasswordPlugin

# Aliases for the patch targets (import binding sites in plugin modules)
_PW = "truenas_tui.plugins.legacy_password.view"
_OTP = "truenas_tui.plugins.onetime_password.view"


class TestOnetimePasswordPlugin:
    def test_calls_generate_with_session_username(self, recording_session, stdscr):
        with patch(f"{_OTP}.message_dialog"):
            OnetimePasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.AUTH_GENERATE_ONETIME_PASSWORD)
        (args, _) = recording_session.called_with(
            Method.AUTH_GENERATE_ONETIME_PASSWORD
        )[0]
        assert args[0] == {"username": recording_session.username}

    def test_otp_displayed_in_message_dialog(self, recording_session, stdscr):
        with patch(f"{_OTP}.message_dialog") as mock_msg:
            OnetimePasswordPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()
        # The OTP value returned by MockSession ('mock-otp-abc123') must appear
        # somewhere in the dialog body string argument.
        dialog_body = mock_msg.call_args[0][2]
        assert "mock-otp-abc123" in dialog_body

    def test_get_label_contains_username(self, recording_session):
        label = OnetimePasswordPlugin().get_label(recording_session)
        assert recording_session.username in label

    def test_error_from_api_shows_dialog(self, recording_session, stdscr):
        recording_session.override(
            Method.AUTH_GENERATE_ONETIME_PASSWORD, RuntimeError("server error")
        )
        # Call side_effect approach: make the call raise
        original_call = recording_session.call

        def raising_call(method, *args, **kwargs):
            if method == Method.AUTH_GENERATE_ONETIME_PASSWORD:
                raise RuntimeError("server error")
            return original_call(method, *args, **kwargs)

        recording_session.call = raising_call

        with patch(f"{_OTP}.message_dialog") as mock_msg:
            OnetimePasswordPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()


class TestPasswordPluginChangePassword:
    """Tests the path where a local administrator already exists."""

    def test_has_local_admin_queried_via_fetch_label(self, recording_session, stdscr):
        # get_label() must trigger USER_HAS_LOCAL_ADMINISTRATOR_SET_UP
        with patch(f"{_PW}.select_dialog", return_value=None):
            PasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.USER_HAS_LOCAL_ADMINISTRATOR_SET_UP)

    def test_admin_list_fetched_when_admin_exists(self, recording_session, stdscr):
        with patch(f"{_PW}.select_dialog", return_value=None):
            PasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.PRIVILEGE_LOCAL_ADMINISTRATORS)

    def test_successful_password_change_calls_user_update(
        self, recording_session, stdscr
    ):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["goodpassword", "goodpassword"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.USER_UPDATE)

    def test_password_update_payload_correct(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["s3cur3pass", "s3cur3pass"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        (args, _) = recording_session.called_with(Method.USER_UPDATE)[0]
        # args = (user_id, {'password': pw})
        assert args[1] == {"password": "s3cur3pass"}

    def test_user_update_uses_correct_admin_id(self, recording_session, stdscr):
        # MockSession returns admin with id=1
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["s3cur3pass", "s3cur3pass"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        (args, _) = recording_session.called_with(Method.USER_UPDATE)[0]
        assert args[0] == 1  # id from _FAKE_ADMINS

    def test_twofactor_disabled_after_password_change(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["s3cur3pass", "s3cur3pass"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.AUTH_TWOFACTOR_UPDATE)
        (args, _) = recording_session.called_with(Method.AUTH_TWOFACTOR_UPDATE)[0]
        assert args[0] == {"enabled": False}

    def test_cancel_admin_select_no_update(self, recording_session, stdscr):
        with patch(f"{_PW}.select_dialog", return_value=None):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)

    def test_cancel_first_password_no_update(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", return_value=None),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)

    def test_empty_first_password_no_update(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", return_value=""),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)

    def test_too_short_password_no_update(self, recording_session, stdscr):
        # Minimum is 8 characters; 'short' is 5
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", return_value="short"),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)

    def test_exactly_min_length_password_accepted(self, recording_session, stdscr):
        # 8 chars exactly should pass
        pw = "exactly8"
        assert len(pw) == 8
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=[pw, pw]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.USER_UPDATE)

    def test_mismatched_passwords_no_update(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["password1", "password2"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)

    def test_cancel_second_password_no_update(self, recording_session, stdscr):
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["goodpassword", None]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UPDATE)


class TestPasswordPluginSetupAdministrator:
    """Tests the path where no local administrator has been set up yet."""

    def _no_admin_session(self):
        from mock_session import RecordingMockSession

        return RecordingMockSession().override(
            Method.USER_HAS_LOCAL_ADMINISTRATOR_SET_UP, False
        )

    def test_setup_admin_called_when_no_admin(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["newpassword", "newpassword"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        assert session.was_called(Method.USER_SETUP_LOCAL_ADMINISTRATOR)

    def test_setup_uses_admin_username_for_index_0(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["newpassword", "newpassword"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        (args, _) = session.called_with(Method.USER_SETUP_LOCAL_ADMINISTRATOR)[0]
        assert args[0] == "admin"

    def test_setup_uses_root_username_for_index_1(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=1),
            patch(f"{_PW}.input_dialog", side_effect=["newpassword", "newpassword"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        (args, _) = session.called_with(Method.USER_SETUP_LOCAL_ADMINISTRATOR)[0]
        assert args[0] == "root"

    def test_setup_passes_password_as_second_arg(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["mynewpass", "mynewpass"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        (args, _) = session.called_with(Method.USER_SETUP_LOCAL_ADMINISTRATOR)[0]
        assert args[1] == "mynewpass"

    def test_cancel_method_select_no_setup(self, stdscr):
        session = self._no_admin_session()
        with patch(f"{_PW}.select_dialog", return_value=None):
            PasswordPlugin().run(stdscr, session)

        assert not session.was_called(Method.USER_SETUP_LOCAL_ADMINISTRATOR)

    def test_mismatched_passwords_no_setup(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["password1", "password2"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        assert not session.was_called(Method.USER_SETUP_LOCAL_ADMINISTRATOR)

    def test_user_update_not_called_in_setup_path(self, stdscr):
        session = self._no_admin_session()
        with (
            patch(f"{_PW}.select_dialog", return_value=0),
            patch(f"{_PW}.input_dialog", side_effect=["newpassword", "newpassword"]),
            patch(f"{_PW}.message_dialog"),
        ):
            PasswordPlugin().run(stdscr, session)

        assert not session.was_called(Method.USER_UPDATE)


_MA = "truenas_tui.plugins.my_account.view"

# Fake 2FA provisioning URI returned by MockSession for USER_RENEW_2FA_SECRET
_FAKE_2FA_URI = (
    "otpauth://totp/admin-mocknas%40TrueNAS"
    "?secret=JBSWY3DPEBLW64TMMQ"
    "&issuer=iXsystems&digits=6&period=30"
)


class TestMyAccountPlugin2FA:
    """Tests for 2FA set-up, renewal, and disable flows in MyAccountPlugin."""

    @pytest.fixture(autouse=True)
    def _patch_curses(self):
        """Patch curses drawing primitives so no real terminal is required."""
        with (
            patch("curses.doupdate"),
            patch("curses.color_pair", return_value=0),
            patch(f"{_MA}.pair", return_value=0),
        ):
            yield

    def test_setup_2fa_calls_renew(self, recording_session, stdscr):
        """Activating 'Set up two-factor authentication' calls USER_RENEW_2FA_SECRET."""
        # Default mock has secret_configured=False → "Set up 2FA" is at index 2.
        # Navigate: DOWN × 2, Enter to activate, Enter to dismiss QR screen, q to exit.
        stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            ord("\n"),  # activate
            ord("\n"),  # dismiss _show_2fa_setup
            ord("q"),  # exit main loop
        ]
        with (
            patch(f"{_MA}._find_qr_tool", return_value="/usr/bin/qr"),
            patch(f"{_MA}._render_qr", return_value="QR\n"),
            patch(f"{_MA}.message_dialog"),
        ):
            MyAccountPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.USER_RENEW_2FA_SECRET)

    def test_setup_2fa_params(self, recording_session, stdscr):
        """USER_RENEW_2FA_SECRET is called with username and correct options dict."""
        stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            ord("\n"),
            ord("\n"),
            ord("q"),
        ]
        with (
            patch(f"{_MA}._find_qr_tool", return_value="/usr/bin/qr"),
            patch(f"{_MA}._render_qr", return_value="QR\n"),
            patch(f"{_MA}.message_dialog"),
        ):
            MyAccountPlugin().run(stdscr, recording_session)

        (args, _) = recording_session.called_with(Method.USER_RENEW_2FA_SECRET)[0]
        assert args[0] == recording_session.username
        assert args[1] == {"otp_digits": 6, "interval": 30}

    def test_disable_2fa_calls_unset(self, recording_session, stdscr):
        """Confirming 'Disable two-factor authentication' calls USER_UNSET_2FA_SECRET."""
        recording_session.override(
            Method.AUTH_ME,
            {
                **recording_session.me,
                "two_factor_config": {
                    "secret_configured": True,
                    "provisioning_uri": None,
                    "interval": 30,
                    "otp_digits": 6,
                },
            },
        )
        # two_fa_configured=True → actions: Change pw(0), OTP(1), Renew(2), Disable(3)
        stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            ord("\n"),  # activate "Disable two-factor authentication"
            ord("q"),  # exit after action completes
        ]
        with (
            patch(f"{_MA}._find_qr_tool", return_value="/usr/bin/qr"),
            patch(f"{_MA}.confirm_dialog", return_value=True),
            patch(f"{_MA}.message_dialog"),
        ):
            MyAccountPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.USER_UNSET_2FA_SECRET)

    def test_disable_2fa_cancel_skips_unset(self, recording_session, stdscr):
        """Cancelling the confirm dialog does NOT call USER_UNSET_2FA_SECRET."""
        recording_session.override(
            Method.AUTH_ME,
            {
                **recording_session.me,
                "two_factor_config": {
                    "secret_configured": True,
                    "provisioning_uri": None,
                    "interval": 30,
                    "otp_digits": 6,
                },
            },
        )
        stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            ord("\n"),  # activate "Disable two-factor authentication"
            ord("q"),  # exit
        ]
        with (
            patch(f"{_MA}._find_qr_tool", return_value="/usr/bin/qr"),
            patch(f"{_MA}.confirm_dialog", return_value=False),
            patch(f"{_MA}.message_dialog"),
        ):
            MyAccountPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.USER_UNSET_2FA_SECRET)

    def test_extract_secret(self):
        """_extract_secret returns the 'secret' query parameter from an otpauth URI."""
        uri = (
            "otpauth://totp/admin%40TrueNAS"
            "?secret=JBSWY3DPEBWW64TM&issuer=iXsystems&digits=6&period=30"
        )
        assert _extract_secret(uri) == "JBSWY3DPEBWW64TM"

    def test_find_qr_tool_none_when_absent(self):
        """_find_qr_tool returns None when neither qr nor qrcode-terminal is on PATH."""
        with patch("shutil.which", return_value=None):
            assert _find_qr_tool() is None

    def test_disabled_action_shows_dialog_not_api(self, recording_session, stdscr):
        """Selecting a disabled 2FA action shows an info dialog, not an API call."""
        # _find_qr_tool returns None → "Set up 2FA" at index 2 is disabled.
        stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_DOWN,
            ord("\n"),  # activate disabled action → message_dialog shown
            ord("q"),  # exit
        ]
        with (
            patch(f"{_MA}._find_qr_tool", return_value=None),
            patch(f"{_MA}.message_dialog") as mock_msg,
        ):
            MyAccountPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()
        assert not recording_session.was_called(Method.USER_RENEW_2FA_SECRET)
