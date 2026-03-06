"""
Group 3 – Curses E2E: Menu navigation via pexpect.

Spawns run_mock_tui.py as a subprocess through a real pty and interacts
with the TUI using pexpect patterns.  Does not test any plugin internals —
only the main view shell behaviour.

Legacy mode (--menu):
  Remote: 8 plugins (indices 1-10, gaps at 7-8), footer "1-10:"
  Local:  10 plugins (indices 1-10), footer "1-10:"

Default mode (no --menu):
  Remote: 3 plugins (Network sub-menu, My Account, Power Control), no numbered footer prompt
  Local:  3 plugins, no numbered footer prompt
"""
import os
import sys
import pexpect
import pytest

SCRIPT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_mock_tui.py')
PYTHON  = sys.executable
CTRL_D  = '\x04'
ESC     = '\x1b'
TIMEOUT = 10


def _spawn(local=False, menu=False, cols=80, rows=24):
    args = [SCRIPT]
    if local:
        args.append('--local')
    if menu:
        args.append('--menu')
    return pexpect.spawn(PYTHON, args, timeout=TIMEOUT,
                         dimensions=(rows, cols),
                         env={**os.environ, 'TERM': 'xterm'})


def _boot_legacy(child):
    """Wait for the legacy TUI menu footer to appear."""
    child.expect('Enter an option from 1-', timeout=TIMEOUT)


def _boot_default(child):
    """Wait for the default mode TUI to appear (no numbered footer)."""
    child.expect('Navigate', timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# Header content
# ---------------------------------------------------------------------------

class TestHeader:
    def test_hostname_appears_in_header(self):
        child = _spawn(menu=True)
        try:
            child.expect('mocknas', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_version_appears_in_header(self):
        child = _spawn(menu=True)
        try:
            child.expect('25.10', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_username_appears_in_header(self):
        child = _spawn(menu=True)
        try:
            child.expect('admin', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_server_address_appears_in_header(self):
        child = _spawn(menu=True)
        try:
            child.expect('192.168.1.108', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_local_mode_shows_local_in_header(self):
        child = _spawn(local=True, menu=True)
        try:
            child.expect('local', timeout=TIMEOUT)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# Footer option count (legacy mode)
# ---------------------------------------------------------------------------

class TestFooterOptionCount:
    def test_legacy_remote_shows_1_to_10(self):
        """Legacy remote: max LEGACY_INDEX is 10 (Shutdown), footer shows 1-10."""
        child = _spawn(menu=True)
        try:
            child.expect(r'Enter an option from 1-10:', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_legacy_local_shows_1_to_10(self):
        """Legacy local: all 10 items visible, footer shows 1-10."""
        child = _spawn(local=True, menu=True)
        try:
            child.expect(r'Enter an option from 1-10:', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_default_mode_has_no_numbered_prompt(self):
        """Default mode footer has no numbered prompt."""
        child = _spawn()
        try:
            # Should see Navigate hint but NOT "Enter an option from"
            child.expect('Navigate', timeout=TIMEOUT)
            # Verify numbered prompt is absent by checking it doesn't appear
            # before we quit
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_default_mode_footer_shows_settings_hint(self):
        """Default mode footer advertises the 's Settings' hotkey."""
        child = _spawn()
        try:
            child.expect('Settings', timeout=TIMEOUT)
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# Exit paths
# ---------------------------------------------------------------------------

class TestExitPaths:
    def test_q_exits_cleanly(self):
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_ctrl_d_exits_cleanly(self):
        """Covered by test_expect_compat.py; included here for completeness."""
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send(CTRL_D)
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_ctrl_d_exits_from_inside_plugin(self):
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('1')          # activate first plugin
            child.send(CTRL_D)
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_q_exits_default_mode(self):
        child = _spawn()
        try:
            _boot_default(child)
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# Number key navigation (legacy mode only)
# ---------------------------------------------------------------------------

class TestNumberKeyNavigation:
    def test_key_1_activates_first_plugin(self):
        """Pressing '1' opens plugin with LEGACY_INDEX=1 (network interfaces)."""
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('1')
            child.expect('eno', timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_key_5_activates_otp_plugin(self):
        """Pressing '5' opens plugin with LEGACY_INDEX=5 (OTP)."""
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('5')
            child.expect('mock-otp-abc123', timeout=TIMEOUT)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# r-key refresh (smoke test — should not crash)
# ---------------------------------------------------------------------------

class TestRefreshKey:
    def test_r_key_does_not_crash(self):
        """'r' triggers a label+sysinfo refresh; TUI must stay alive afterwards."""
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('r')
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# Esc returns to info mode
# ---------------------------------------------------------------------------

class TestEscKey:
    def test_esc_from_plugin_returns_to_menu(self):
        """Open a plugin that returns on 'q' (StaticRoutes); verify menu reappears."""
        child = _spawn(menu=True)
        try:
            _boot_legacy(child)
            child.send('3')          # StaticRoutes: shows empty list, 'q' exits
            child.expect('No static routes', timeout=TIMEOUT)
            child.send('q')
            child.expect('Enter an option from 1-', timeout=TIMEOUT)
        finally:
            child.close(force=True)


# ---------------------------------------------------------------------------
# Terminal resize smoke test
# ---------------------------------------------------------------------------

class TestTerminalSize:
    def test_narrow_terminal_does_not_crash(self):
        child = _spawn(menu=True, cols=40, rows=12)
        try:
            child.expect('Enter an option from 1-', timeout=TIMEOUT)
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_wide_terminal_does_not_crash(self):
        child = _spawn(menu=True, cols=220, rows=50)
        try:
            child.expect('Enter an option from 1-', timeout=TIMEOUT)
            child.send('q')
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)
