"""
Group 2 – Interface Mapping: Reboot, Shutdown, ResetConfig plugins.

Strategy: patch dialog helpers at their import binding sites inside each
plugin module; use RecordingMockSession to assert the right API method was
(or was not) called with the right arguments.
"""

import pytest
from unittest.mock import patch

from truenas_tui.api_methods import Method
from truenas_tui.plugins.legacy_reboot.view import RebootPlugin
from truenas_tui.plugins.legacy_shutdown.view import ShutdownPlugin
from truenas_tui.plugins.legacy_reset_config.view import ResetConfigPlugin


class TestRebootPlugin:
    def test_requires_full_admin_write(self):
        assert "FULL_ADMIN" in RebootPlugin.REQUIRED_WRITE_ROLES

    def test_confirmed_calls_system_reboot(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reboot.view.input_dialog",
                return_value="Maintenance window",
            ) as _,
            patch(
                "truenas_tui.plugins.legacy_reboot.view.confirm_dialog",
                return_value=True,
            ),
            patch("truenas_tui.plugins.legacy_reboot.view.message_dialog"),
        ):
            RebootPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.SYSTEM_REBOOT)

    def test_reason_stripped_before_api_call(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reboot.view.input_dialog",
                return_value="  Maintenance  ",
            ),
            patch(
                "truenas_tui.plugins.legacy_reboot.view.confirm_dialog",
                return_value=True,
            ),
            patch("truenas_tui.plugins.legacy_reboot.view.message_dialog"),
        ):
            RebootPlugin().run(stdscr, recording_session)

        (args, _) = recording_session.called_with(Method.SYSTEM_REBOOT)[0]
        assert args[0] == {"reason": "Maintenance"}

    def test_success_dialog_shown_after_reboot(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reboot.view.input_dialog",
                return_value="reason",
            ),
            patch(
                "truenas_tui.plugins.legacy_reboot.view.confirm_dialog",
                return_value=True,
            ),
            patch("truenas_tui.plugins.legacy_reboot.view.message_dialog") as mock_msg,
        ):
            RebootPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()

    def test_cancel_at_reason_dialog_no_api_call(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_reboot.view.input_dialog", return_value=None
        ):
            RebootPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_REBOOT)

    def test_blank_reason_treated_as_cancel(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_reboot.view.input_dialog", return_value="   "
        ):
            RebootPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_REBOOT)

    def test_empty_reason_treated_as_cancel(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_reboot.view.input_dialog", return_value=""
        ):
            RebootPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_REBOOT)

    def test_cancel_at_confirm_dialog_no_api_call(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reboot.view.input_dialog",
                return_value="reason",
            ),
            patch(
                "truenas_tui.plugins.legacy_reboot.view.confirm_dialog",
                return_value=False,
            ),
        ):
            RebootPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_REBOOT)


class TestShutdownPlugin:
    def test_requires_full_admin_write(self):
        assert "FULL_ADMIN" in ShutdownPlugin.REQUIRED_WRITE_ROLES

    def test_confirmed_calls_system_shutdown(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.input_dialog",
                return_value="Planned maintenance",
            ),
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.confirm_dialog",
                return_value=True,
            ),
            patch("truenas_tui.plugins.legacy_shutdown.view.message_dialog"),
        ):
            ShutdownPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.SYSTEM_SHUTDOWN)

    def test_reason_stripped_before_api_call(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.input_dialog",
                return_value="  Hardware swap  ",
            ),
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.confirm_dialog",
                return_value=True,
            ),
            patch("truenas_tui.plugins.legacy_shutdown.view.message_dialog"),
        ):
            ShutdownPlugin().run(stdscr, recording_session)

        (args, _) = recording_session.called_with(Method.SYSTEM_SHUTDOWN)[0]
        assert args[0] == {"reason": "Hardware swap"}

    def test_cancel_at_reason_no_api_call(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_shutdown.view.input_dialog", return_value=None
        ):
            ShutdownPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_SHUTDOWN)

    def test_blank_reason_treated_as_cancel(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_shutdown.view.input_dialog", return_value=""
        ):
            ShutdownPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_SHUTDOWN)

    def test_cancel_at_confirm_no_api_call(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.input_dialog",
                return_value="reason",
            ),
            patch(
                "truenas_tui.plugins.legacy_shutdown.view.confirm_dialog",
                return_value=False,
            ),
        ):
            ShutdownPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_SHUTDOWN)


class TestResetConfigPlugin:
    def test_requires_full_admin_write(self):
        assert "FULL_ADMIN" in ResetConfigPlugin.REQUIRED_WRITE_ROLES

    def test_correct_string_calls_system_config_reset(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.confirm_dialog",
                return_value=True,
            ),
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.input_dialog",
                return_value="RESET",
            ),
            patch("truenas_tui.plugins.legacy_reset_config.view.message_dialog"),
        ):
            ResetConfigPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.SYSTEM_CONFIG_RESET)

    def test_first_confirm_cancel_no_api_call(self, recording_session, stdscr):
        with patch(
            "truenas_tui.plugins.legacy_reset_config.view.confirm_dialog",
            return_value=False,
        ):
            ResetConfigPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_CONFIG_RESET)

    @pytest.mark.parametrize(
        "wrong",
        [
            "reset",  # lowercase
            "Reset",  # mixed case
            "RESET ",  # trailing space
            " RESET",  # leading space
            "",  # empty
            "yes",  # wrong word
            "RESET\n",  # embedded newline
        ],
    )
    def test_wrong_string_no_api_call(self, wrong, stdscr):
        from mock_session import RecordingMockSession

        rs = RecordingMockSession()
        with (
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.confirm_dialog",
                return_value=True,
            ),
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.input_dialog",
                return_value=wrong,
            ),
            patch("truenas_tui.plugins.legacy_reset_config.view.message_dialog"),
        ):
            ResetConfigPlugin().run(stdscr, rs)

        assert not rs.was_called(Method.SYSTEM_CONFIG_RESET), (
            f"Should not reset for confirmation string {wrong!r}"
        )

    def test_none_input_no_api_call(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.confirm_dialog",
                return_value=True,
            ),
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.input_dialog",
                return_value=None,
            ),
            patch("truenas_tui.plugins.legacy_reset_config.view.message_dialog"),
        ):
            ResetConfigPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.SYSTEM_CONFIG_RESET)

    def test_cancel_message_shown_for_wrong_string(self, recording_session, stdscr):
        with (
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.confirm_dialog",
                return_value=True,
            ),
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.input_dialog",
                return_value="wrong",
            ),
            patch(
                "truenas_tui.plugins.legacy_reset_config.view.message_dialog"
            ) as mock_msg,
        ):
            ResetConfigPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()
