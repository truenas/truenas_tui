"""
Unit tests for truenas_tui/tui/main_view.py.

Tests patch signal.signal, curses functions, and colour pair calls so that no
real terminal is required.
"""

import curses
import signal
from unittest.mock import MagicMock, patch, call

import pytest

from truenas_tui.tui.main_view import MainView, _fmt_bytes, _fmt_load
from truenas_tui.tui import HardExit
from truenas_tui.api_methods import Method


@pytest.fixture(autouse=True)
def patch_curses_acs(monkeypatch):
    """curses.ACS_* constants are only available after curses.initscr(); mock them."""
    monkeypatch.setattr(curses, "ACS_VLINE", 0, raising=False)


def test_fmt_bytes_gib():
    # 1 GiB = 1073741824 bytes
    assert _fmt_bytes(1073741824) == "1.0 GiB"


def test_fmt_bytes_64_gib():
    assert _fmt_bytes(64 * 1024**3) == "64.0 GiB"


def test_fmt_bytes_partial():
    # 512 MiB = 0.5 GiB
    assert _fmt_bytes(512 * 1024**2) == "0.5 GiB"


def test_fmt_load_three_values():
    result = _fmt_load([0.1, 0.5, 1.2])
    assert "0.10" in result
    assert "0.50" in result
    assert "1.20" in result


def test_fmt_load_single_value():
    result = _fmt_load([0.25])
    assert "0.25" in result


def test_fmt_load_empty():
    # Should not raise with empty list (slices to empty)
    result = _fmt_load([])
    assert result == ""


def _make_session(
    username="admin",
    hostname="testnas",
    version="25.10.0",
    role_label="FULL_ADMIN",
    server="192.168.1.108",
):
    session = MagicMock()
    session.username = username
    session.hostname = hostname
    session.version = version
    session.role_label = role_label
    session.config.server = server
    sysinfo = {
        "version": version,
        "hostname": hostname,
        "loadavg": [0.1, 0.2, 0.3],
        "physmem": 1073741824,
        "ecc_memory": False,
        "model": "Test CPU",
        "cores": 4,
        "physical_cores": 2,
        "uptime": "1 day",
        "timezone": "UTC",
        "system_product": None,
        "system_serial": None,
        "system_manufacturer": None,
    }
    session.system_info = sysinfo
    # Ensure call() always returns a proper dict so system_info stays valid
    # after reassignment inside the tick/refresh handlers.
    session.call.return_value = sysinfo
    session.roles = {"FULL_ADMIN"}
    return session


def _make_plugin(label="Test Plugin", description="A test plugin", can_write=True):
    plugin = MagicMock()
    plugin.get_label.return_value = label
    plugin.get_description.return_value = description
    plugin.can_write.return_value = can_write
    plugin.needs_refresh.return_value = False
    return plugin


def _make_view(stdscr, session, plugins, *, patches=True, menu_mode=False):
    """Create a MainView with signal.signal patched."""
    with patch("signal.signal"):
        view = MainView(stdscr, session, plugins, menu_mode=menu_mode)
    return view


def _run_with_patches(view, stdscr, extra_patches=None):
    """Run the MainView loop with standard curses patches applied."""
    patchlist = [
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("curses.endwin"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ]
    if extra_patches:
        patchlist.extend(extra_patches)

    cms = [p.__enter__() for p in patchlist]
    try:
        view.run()
    finally:
        for i, p in enumerate(patchlist):
            p.__exit__(None, None, None)


def test_draw_header_shows_hostname(stdscr):
    session = _make_session(hostname="bobnas")
    view = _make_view(stdscr, session, [])
    with (
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view._draw_header(24, 80)
    # addstr should have been called and include hostname
    calls = stdscr.addstr.call_args_list
    assert any("bobnas" in str(c) for c in calls)


def test_draw_header_shows_server(stdscr):
    session = _make_session(server="10.0.0.1")
    view = _make_view(stdscr, session, [])
    with (
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view._draw_header(24, 80)
    calls = stdscr.addstr.call_args_list
    assert any("10.0.0.1" in str(c) for c in calls)


def test_draw_header_local_mode(stdscr):
    session = _make_session(server=None)
    view = _make_view(stdscr, session, [])
    with (
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view._draw_header(24, 80)
    calls = stdscr.addstr.call_args_list
    assert any("local" in str(c) for c in calls)


def test_draw_header_root_warning(stdscr):
    session = _make_session(username="root")
    view = _make_view(stdscr, session, [])
    with (
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view._draw_header(24, 80)
    # root warning should appear
    all_calls_str = str(stdscr.addstr.call_args_list)
    assert "WARNING" in all_calls_str or "root" in all_calls_str


def test_draw_footer_shows_plugin_count(stdscr):
    session = _make_session()
    plugins = [_make_plugin(f"Plugin {i}") for i in range(8)]
    for i, p in enumerate(plugins):
        p.LEGACY_INDEX = i + 1
    view = _make_view(stdscr, session, plugins, menu_mode=True)
    with patch("truenas_tui.tui.main_view.pair", return_value=0):
        view._draw_footer(24, 80)
    calls = stdscr.addstr.call_args_list
    assert any("1-8" in str(c) for c in calls)


def test_draw_footer_info_mode_hints(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    view._info_mode = True
    with patch("truenas_tui.tui.main_view.pair", return_value=0):
        view._draw_footer(24, 80)
    calls_str = str(stdscr.addstr.call_args_list)
    assert "Refresh" in calls_str or "refresh" in calls_str.lower()


def test_draw_footer_desc_mode_hints(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    view._info_mode = False
    with patch("truenas_tui.tui.main_view.pair", return_value=0):
        view._draw_footer(24, 80)
    calls_str = str(stdscr.addstr.call_args_list)
    # Desc mode shows Esc hint
    assert "Esc" in calls_str or "Info" in calls_str


def test_q_exits(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    stdscr.getch.side_effect = [ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()  # should return without raising


def test_Q_exits(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    stdscr.getch.side_effect = [ord("Q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()


def test_ctrl_d_raises_hard_exit(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    stdscr.getch.side_effect = [4]  # Ctrl+D

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            view.run()


def test_number_key_activates_plugin(stdscr):
    session = _make_session()
    plugin = _make_plugin()
    plugin.LEGACY_INDEX = 1
    view = _make_view(stdscr, session, [plugin], menu_mode=True)
    # '1' activates plugin with LEGACY_INDEX=1, then 'q' quits
    stdscr.getch.side_effect = [ord("1"), ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    plugin.run.assert_called_once_with(stdscr, session)


def test_number_key_out_of_range(stdscr):
    session = _make_session()
    plugin = _make_plugin()
    view = _make_view(stdscr, session, [plugin])
    # '9' when only 1 plugin → no activation, then 'q'
    stdscr.getch.side_effect = [ord("9"), ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    plugin.run.assert_not_called()


def test_up_down_navigation(stdscr):
    session = _make_session()
    p1 = _make_plugin("Plugin 1")
    p2 = _make_plugin("Plugin 2")
    view = _make_view(stdscr, session, [p1, p2])
    assert view.selected == 0

    stdscr.getch.side_effect = [curses.KEY_DOWN, ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    assert view.selected == 1


def test_up_at_top_stays(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    assert view.selected == 0

    stdscr.getch.side_effect = [curses.KEY_UP, ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    assert view.selected == 0  # stayed


def test_esc_switches_to_info_mode(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    view._info_mode = False  # start in desc mode

    stdscr.getch.side_effect = [27, ord("q")]  # Esc → info mode, q → quit

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    assert view._info_mode is True


def test_r_key_refreshes_plugins(stdscr):
    session = _make_session()
    plugin = _make_plugin()
    view = _make_view(stdscr, session, [plugin])

    stdscr.getch.side_effect = [ord("r"), ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    plugin.refresh.assert_called_once_with(session)


def test_enter_activates_selected(stdscr):
    session = _make_session()
    plugin = _make_plugin()
    view = _make_view(stdscr, session, [plugin])

    stdscr.getch.side_effect = [ord("\n"), ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    plugin.run.assert_called_once_with(stdscr, session)


def test_plugin_run_exception_shows_dialog(stdscr):
    session = _make_session()
    plugin = _make_plugin()
    plugin.run.side_effect = Exception("Something broke")
    view = _make_view(stdscr, session, [plugin])

    stdscr.getch.side_effect = [ord("\n"), ord("q")]

    # message_dialog is imported inline inside _activate_selected, so patch at source
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
        patch("truenas_tui.tui.dialogs.message_dialog") as mock_msg,
    ):
        view.run()

    mock_msg.assert_called_once()


def test_timeout_tick_triggers_info_refresh(stdscr):
    """On a -1 (timeout) tick when in info mode, system_info is refreshed."""
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin()])
    view._info_mode = True
    # Force immediate refresh by setting next_refresh to past
    view._info_next_refresh = 0.0

    stdscr.getch.side_effect = [-1, ord("q")]  # tick, then quit

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    session.call.assert_called_with(Method.SYSTEM_INFO)


def test_timeout_tick_plugin_refresh(stdscr):
    """On a -1 tick in desc mode, needs_refresh() is checked."""
    session = _make_session()
    plugin = _make_plugin()
    plugin.needs_refresh.return_value = True
    view = _make_view(stdscr, session, [plugin])
    view._info_mode = False
    view._info_next_refresh = float("inf")  # prevent info refresh

    stdscr.getch.side_effect = [-1, ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    plugin.refresh.assert_called_with(session)


def test_handle_resize_sets_pending(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [])
    assert view._resize_pending is False
    view._handle_resize(signal.SIGWINCH, None)
    assert view._resize_pending is True


def test_down_navigation_switches_to_desc_mode(stdscr):
    session = _make_session()
    view = _make_view(stdscr, session, [_make_plugin(), _make_plugin()])
    view._info_mode = True

    stdscr.getch.side_effect = [curses.KEY_DOWN, ord("q")]

    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("curses.doupdate"),
        patch("truenas_tui.tui.main_view.pair", return_value=0),
    ):
        view.run()

    assert view._info_mode is False
