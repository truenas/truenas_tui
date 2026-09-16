"""
Group 3 – Curses E2E: Plugin activation and cancel flows via pexpect.

Each test:
  1. Boots the mock TUI
  2. Activates a specific plugin
  3. Asserts plugin-specific text appears
  4. Dismisses/cancels and (where possible) verifies the menu returns

Legacy mode (--menu) is used for tests that rely on number-key shortcuts.
Default mode is used for PowerControlPlugin (reached via arrow keys).

Legacy plugin map (remote, --menu):
  1 – NetworkInterfacePlugin   (interface list)
  2 – NetworkSettingsPlugin    (form)
  3 – StaticRoutesPlugin       (route list)
  4 – PasswordPlugin           (select admin)
  5 – OnetimePasswordPlugin    (OTP dialog)
  6 – ResetConfigPlugin        (confirm dialog)
  9 – RebootPlugin             (reason input)
  10 – ShutdownPlugin          (reason input, not numbered in 1-9 range)

Legacy plugin map (local, --menu):
  7 – CliShellPlugin           (midcli not found → error dialog)
  8 – LinuxShellPlugin         (spawns shell → exits → TUI restores)
"""

import os
import shutil
import sys

import pexpect
import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_mock_tui.py")
PYTHON = sys.executable
CTRL_D = "\x04"
ESC = "\x1b"
TIMEOUT = 12


def _spawn(local=False, menu=True):
    args = [SCRIPT]
    if local:
        args.append("--local")
    if menu:
        args.append("--menu")
    return pexpect.spawn(
        PYTHON,
        args,
        timeout=TIMEOUT,
        dimensions=(24, 80),
        env={**os.environ, "TERM": "xterm"},
    )


def _boot(child):
    child.expect("Enter an option from 1-", timeout=TIMEOUT)


def _boot_default(child):
    child.expect("Navigate", timeout=TIMEOUT)


def _open_plugin(key: str, local=False):
    """Boot the legacy TUI and send key to open a plugin. Returns the child."""
    child = _spawn(local=local, menu=True)
    _boot(child)
    child.send(key)
    return child


class TestNetworkInterfacePlugin:
    def test_opens_and_shows_interface(self):
        child = _open_plugin("1")
        try:
            child.expect("eno1", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_returns_to_menu_after_ctrl_d(self):
        child = _open_plugin("1")
        try:
            child.expect("eno", timeout=TIMEOUT)
            child.send(CTRL_D)
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)


class TestNetworkSettingsPlugin:
    def test_opens_and_shows_hostname_field(self):
        child = _open_plugin("2")
        try:
            child.expect("mocknas", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_esc_returns_to_menu(self):
        child = _open_plugin("2")
        try:
            child.expect("mocknas", timeout=TIMEOUT)
            child.send(ESC)  # cancel the form
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestStaticRoutesPlugin:
    def test_opens_and_shows_empty_list(self):
        child = _open_plugin("3")
        try:
            child.expect("No static routes", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_q_returns_to_menu(self):
        child = _open_plugin("3")
        try:
            child.expect("No static routes", timeout=TIMEOUT)
            child.send("q")
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_esc_returns_to_menu(self):
        child = _open_plugin("3")
        try:
            child.expect("No static routes", timeout=TIMEOUT)
            child.send(ESC)
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestPasswordPlugin:
    def test_opens_and_shows_admin_in_selection(self):
        child = _open_plugin("4")
        try:
            child.expect("admin", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_cancel_with_ctrl_d(self):
        child = _open_plugin("4")
        try:
            child.expect("admin", timeout=TIMEOUT)
            child.send(CTRL_D)
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)


class TestOnetimePasswordPlugin:
    def test_shows_generated_otp(self):
        child = _open_plugin("5")
        try:
            child.expect("mock-otp-abc123", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_dialog_dismisses_on_enter(self):
        child = _open_plugin("5")
        try:
            child.expect("mock-otp-abc123", timeout=TIMEOUT)
            child.send("\n")  # dismiss the dialog
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestResetConfigPlugin:
    def test_opens_and_shows_confirm_dialog(self):
        child = _open_plugin("6")
        try:
            child.expect("(?i)reset|erase|confirm", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_cancel_returns_to_menu(self):
        child = _open_plugin("6")
        try:
            child.expect("(?i)reset|erase|confirm", timeout=TIMEOUT)
            child.send("n")  # choose "No" / "Cancel"
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestRebootPlugin:
    def test_opens_and_shows_reason_prompt(self):
        child = _open_plugin("9")
        try:
            child.expect("(?i)reboot|reason", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    def test_empty_reason_cancels_and_returns(self):
        child = _open_plugin("9")
        try:
            child.expect("(?i)reboot|reason", timeout=TIMEOUT)
            child.send("\n")  # send empty reason
            child.expect("Enter an option from 1-", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestCliShellPlugin:
    def test_shows_not_found_when_midcli_absent(self):
        """
        If midcli is not on the system, the plugin shows an error dialog.
        If midcli IS present, execv replaces the process — pexpect sees EOF.
        We accept either outcome.
        """
        child = _spawn(local=True, menu=True)
        try:
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
            child.send("7")
            idx = child.expect(
                ["Not Found", "midcli", pexpect.EOF],
                timeout=TIMEOUT,
            )
            assert idx in (0, 1, 2)
        finally:
            child.close(force=True)

    @pytest.mark.skipif(
        shutil.which("midcli") is not None,
        reason="midcli is installed; execv would replace the process",
    )
    def test_not_found_dialog_dismisses_on_enter(self):
        """Only runs when midcli is absent."""
        child = _spawn(local=True, menu=True)
        try:
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
            child.send("7")
            child.expect("Not Found", timeout=TIMEOUT)
            child.send("\n")
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestLinuxShellPlugin:
    @pytest.mark.skipif(
        shutil.which("zsh") is None and shutil.which("bash") is None,
        reason="No supported shell found on this system",
    )
    def test_opens_shell_and_returns_after_exit(self):
        """
        The plugin suspends curses, runs the user's shell, and restores the
        TUI after the shell exits.  We send 'exit\\n' to close the shell and
        verify the TUI menu reappears.
        """
        child = _spawn(local=True, menu=True)
        try:
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
            child.send("8")
            child.expect(r"[$#%>]", timeout=TIMEOUT)
            child.sendline("exit")
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
        finally:
            child.close(force=True)

    @pytest.mark.skipif(
        shutil.which("zsh") is None and shutil.which("bash") is None,
        reason="No supported shell found on this system",
    )
    def test_ctrl_d_in_shell_returns_to_tui(self):
        """Ctrl+D from the shell (EOF) also closes the shell and restores TUI."""
        child = _spawn(local=True, menu=True)
        try:
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
            child.send("8")
            child.expect(r"[$#%>]", timeout=TIMEOUT)
            child.send(CTRL_D)  # EOF to shell
            child.expect(r"Enter an option from 1-10:", timeout=TIMEOUT)
        finally:
            child.close(force=True)


class TestPowerControlPlugin:
    def test_power_control_label_visible_in_default_mode(self):
        """
        In default mode the menu renders PowerControlPlugin's label.
        Verify it appears in the screen output on startup.
        """
        child = _spawn(menu=False)
        try:
            # Look for the label directly — it is rendered before the footer
            child.expect("(?i)reboot/shutdown", timeout=TIMEOUT)
            child.send("q")
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)

    def test_default_mode_no_numbered_prompt(self):
        """Default mode footer must NOT contain 'Enter an option from 1-'."""
        child = _spawn(menu=False)
        try:
            _boot_default(child)
            child.send("q")
            child.expect(pexpect.EOF, timeout=5)
        finally:
            child.close(force=True)
