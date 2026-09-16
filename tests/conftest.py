"""
Shared pytest fixtures for the truenas_tui test suite.

Groups:
  local_session        – MockSession with server=None (LOCAL_ONLY plugins visible)
  recording_session    – RecordingMockSession (remote by default)
  stdscr               – MagicMock satisfying all curses stdscr interactions
"""

from unittest.mock import MagicMock

import pytest

from mock_session import MockSession, RecordingMockSession

# test_live_readonly.py requires a live TrueNAS server and a --config flag.
# Exclude it from automatic collection so plain `pytest` doesn't fail.
collect_ignore = ["test_live_readonly.py"]


@pytest.fixture
def local_session():
    """MockSession presenting as a local AF-UNIX connection (server=None)."""
    s = MockSession()
    s.config.server = None
    return s


@pytest.fixture
def recording_session():
    """RecordingMockSession in remote mode; records all session.call() calls."""
    return RecordingMockSession()


@pytest.fixture
def mock_win():
    """MagicMock curses window with sensible defaults (used for dialog tests)."""
    win = MagicMock()
    win.getmaxyx.return_value = (10, 50)
    return win


@pytest.fixture
def stdscr():
    """
    MagicMock that satisfies every curses stdscr interaction used by plugins.

    getmaxyx() returns (24, 80) by default.  Individual tests can adjust this
    via stdscr.getmaxyx.return_value = (rows, cols).
    """
    win = MagicMock()
    win.getmaxyx.return_value = (24, 80)
    return win
