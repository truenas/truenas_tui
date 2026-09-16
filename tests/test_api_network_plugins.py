"""
Group 2 – Interface Mapping: NetworkSettings and StaticRoutes plugins.

NetworkSettingsPlugin uses Form.run() — patched at the class level so the
form never renders to a real terminal.

StaticRoutesPlugin has an inner while loop driven by stdscr.getch().  We
control the loop by setting stdscr.getch.side_effect to an iterator that
emits a key sequence ending in 'q'.  curses.curs_set and the color helper
pair() are also patched to avoid terminal initialisation errors.
"""

import curses
import pytest
from unittest.mock import patch, MagicMock

from truenas_tui.api_methods import Method
from truenas_tui.plugins.network_settings.view import NetworkSettingsPlugin
from truenas_tui.plugins.static_routes.view import StaticRoutesPlugin

_NS = "truenas_tui.plugins.network_settings.view"
_SR = "truenas_tui.plugins.static_routes.view"


class TestNetworkSettingsPlugin:
    def test_reads_network_config_on_open(self, recording_session, stdscr):
        with patch(f"{_NS}.Form") as MockForm, patch(f"{_NS}.message_dialog"):
            MockForm.return_value.run.return_value = None
            NetworkSettingsPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.NETWORK_CONFIGURATION_CONFIG)

    def test_form_pre_populated_with_current_config(self, recording_session, stdscr):
        """Form fields should be constructed with values from config response."""
        captured_fields = []

        def capture_form(win, title, fields):
            captured_fields.extend(fields)
            m = MagicMock()
            m.run.return_value = None
            return m

        with (
            patch(f"{_NS}.Form", side_effect=capture_form),
            patch(f"{_NS}.message_dialog"),
        ):
            NetworkSettingsPlugin().run(stdscr, recording_session)

        field_values = {f.key: f.value for f in captured_fields}
        assert field_values.get("hostname") == "mocknas"
        assert field_values.get("domain") == "test.local"
        assert field_values.get("ipv4gateway") == "192.168.1.1"

    def test_save_calls_network_config_update(self, recording_session, stdscr):
        updated = {
            "hostname": "newnas",
            "domain": "new.local",
            "ipv4gateway": "",
            "ipv6gateway": "",
            "nameserver1": "",
            "nameserver2": "",
            "nameserver3": "",
        }
        with patch(f"{_NS}.Form") as MockForm, patch(f"{_NS}.message_dialog"):
            MockForm.return_value.run.return_value = updated
            NetworkSettingsPlugin().run(stdscr, recording_session)

        assert recording_session.was_called(Method.NETWORK_CONFIGURATION_UPDATE)
        (args, _) = recording_session.called_with(Method.NETWORK_CONFIGURATION_UPDATE)[
            0
        ]
        assert args[0] == updated

    def test_cancel_skips_update(self, recording_session, stdscr):
        with patch(f"{_NS}.Form") as MockForm, patch(f"{_NS}.message_dialog"):
            MockForm.return_value.run.return_value = None
            NetworkSettingsPlugin().run(stdscr, recording_session)

        assert not recording_session.was_called(Method.NETWORK_CONFIGURATION_UPDATE)

    def test_success_message_shown_after_save(self, recording_session, stdscr):
        with (
            patch(f"{_NS}.Form") as MockForm,
            patch(f"{_NS}.message_dialog") as mock_msg,
        ):
            MockForm.return_value.run.return_value = {"hostname": "x"}
            NetworkSettingsPlugin().run(stdscr, recording_session)

        mock_msg.assert_called_once()


def _run_static_routes(plugin, stdscr, session, keys):
    """
    Run StaticRoutesPlugin.run() with a controlled key sequence.

    curses.curs_set and the pair() color helper are patched to avoid
    terminal errors.  keys is a list of integer key codes; 'q' (27 / ord('q'))
    must appear last to exit the loop.
    """
    stdscr.getch.side_effect = iter(keys)
    with (
        patch("curses.curs_set"),
        patch(f"{_SR}.pair", return_value=0),
        patch(f"{_SR}.colors"),
    ):
        plugin.run(stdscr, session)


def _session_with_route(route=None):
    """RecordingMockSession pre-loaded with one static route."""
    from mock_session import RecordingMockSession

    r = route or {
        "id": 42,
        "destination": "10.0.0.0/8",
        "gateway": "192.168.1.1",
        "description": "test",
    }
    return RecordingMockSession().override(Method.STATICROUTE_QUERY, [r])


class TestStaticRoutesPlugin:
    def test_queries_routes_on_open(self, recording_session, stdscr):
        _run_static_routes(
            StaticRoutesPlugin(), stdscr, recording_session, keys=[ord("q")]
        )
        assert recording_session.was_called(Method.STATICROUTE_QUERY)

    def test_add_route_calls_create(self, stdscr):
        session = (
            _session_with_route.__func__()
            if hasattr(_session_with_route, "__func__")
            else _session_with_route()
        )
        from mock_session import RecordingMockSession

        session = RecordingMockSession()
        new_route = {
            "destination": "172.16.0.0/12",
            "gateway": "192.168.0.1",
            "description": "vpn",
        }
        with patch(f"{_SR}.Form") as MockForm, patch(f"{_SR}.message_dialog"):
            MockForm.return_value.run.return_value = new_route
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("a"), ord("q")]
            )

        assert session.was_called(Method.STATICROUTE_CREATE)
        (args, _) = session.called_with(Method.STATICROUTE_CREATE)[0]
        assert args[0] == new_route

    def test_add_route_cancel_no_create(self, stdscr):
        from mock_session import RecordingMockSession

        session = RecordingMockSession()
        with patch(f"{_SR}.Form") as MockForm:
            MockForm.return_value.run.return_value = None
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("a"), ord("q")]
            )

        assert not session.was_called(Method.STATICROUTE_CREATE)

    def test_delete_confirmed_calls_delete(self, stdscr):
        route = {
            "id": 7,
            "destination": "10.0.0.0/8",
            "gateway": "192.168.1.1",
            "description": "",
        }
        session = _session_with_route(route)
        with (
            patch(f"{_SR}.confirm_dialog", return_value=True),
            patch(f"{_SR}.message_dialog"),
        ):
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("d"), ord("q")]
            )

        assert session.was_called(Method.STATICROUTE_DELETE)
        (args, _) = session.called_with(Method.STATICROUTE_DELETE)[0]
        assert args[0] == 7  # route id

    def test_delete_cancelled_no_delete(self, stdscr):
        route = {
            "id": 7,
            "destination": "10.0.0.0/8",
            "gateway": "192.168.1.1",
            "description": "",
        }
        session = _session_with_route(route)
        with patch(f"{_SR}.confirm_dialog", return_value=False):
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("d"), ord("q")]
            )

        assert not session.was_called(Method.STATICROUTE_DELETE)

    def test_delete_on_empty_list_no_delete(self, recording_session, stdscr):
        # Empty route list — 'd' key should do nothing
        _run_static_routes(
            StaticRoutesPlugin(), stdscr, recording_session, keys=[ord("d"), ord("q")]
        )
        assert not recording_session.was_called(Method.STATICROUTE_DELETE)

    def test_edit_route_calls_update(self, stdscr):
        route = {
            "id": 5,
            "destination": "10.0.0.0/8",
            "gateway": "192.168.1.1",
            "description": "old",
        }
        session = _session_with_route(route)
        updated = {
            "destination": "10.0.0.0/8",
            "gateway": "10.0.0.1",
            "description": "updated",
        }
        with patch(f"{_SR}.Form") as MockForm, patch(f"{_SR}.message_dialog"):
            MockForm.return_value.run.return_value = updated
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("\n"), ord("q")]
            )

        assert session.was_called(Method.STATICROUTE_UPDATE)
        (args, _) = session.called_with(Method.STATICROUTE_UPDATE)[0]
        assert args[0] == 5  # route id
        assert args[1] == updated  # new payload

    def test_edit_route_cancel_no_update(self, stdscr):
        route = {
            "id": 5,
            "destination": "10.0.0.0/8",
            "gateway": "192.168.1.1",
            "description": "",
        }
        session = _session_with_route(route)
        with patch(f"{_SR}.Form") as MockForm:
            MockForm.return_value.run.return_value = None
            _run_static_routes(
                StaticRoutesPlugin(), stdscr, session, keys=[ord("\n"), ord("q")]
            )

        assert not session.was_called(Method.STATICROUTE_UPDATE)

    def test_esc_exits_loop(self, recording_session, stdscr):
        _run_static_routes(
            StaticRoutesPlugin(), stdscr, recording_session, keys=[27]
        )  # ESC
        # Just verify it completed (no StopIteration / hang)
        assert recording_session.was_called(Method.STATICROUTE_QUERY)
