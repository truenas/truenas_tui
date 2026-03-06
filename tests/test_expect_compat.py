#!/usr/bin/env python3
"""
Verifies that the TUI is compatible with the pexpect patterns used by
ixnode/expect.py for boot detection and console interaction.

Reproduces wait_for_boot() and _find_ip_addresses() verbatim from
ixnode/expect.py, substituting only the spawn call.

Run with:
    python3 tests/test_expect_compat.py
"""
import ipaddress
import os
import sys
import pexpect

CONTROL_D     = '\x04'
SCRIPT        = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_mock_tui.py')
PYTHON        = sys.executable
BOOT_PATTERNS = ["The web user interface is at", "Enter an option from 1-"]


def _spawn():
    return pexpect.spawn(PYTHON, [SCRIPT, '--menu'], timeout=10, dimensions=(24, 80),
                         env={**os.environ, 'TERM': 'xterm'})


# ---------------------------------------------------------------------------
# ixnode/expect.py logic copied verbatim (spawn substituted)
# ---------------------------------------------------------------------------

def _wait_for_boot(timeout=10):
    """Mirrors ixnode wait_for_boot()."""
    child = _spawn()
    child.sendline()
    index = child.expect(BOOT_PATTERNS, timeout=timeout)
    if index in [0, 1]:
        child.close(force=True)
        return True
    child.close(force=True)
    raise TimeoutError("boot not detected")


def _find_ip_addresses(itimeout=5, timeout=30):
    """Mirrors ixnode _find_ip_addresses()."""
    ips = set()
    child = _spawn()
    try:
        child.sendline()
        while timeout > 0:
            index = child.expect(BOOT_PATTERNS, timeout=itimeout)
            timeout -= itimeout
            if index in [0, 1]:
                if index == 1:
                    child.sendline(CONTROL_D)
                else:
                    try:
                        while child.expect(["http://", "https://"], timeout=1) in [0, 1]:
                            i = child.expect([":"], timeout=1)
                            timeout -= 2
                            if i == 0:
                                for line in child.before.decode('utf-8').split('\n'):
                                    addr = line.strip()
                                    try:
                                        ipaddress.ip_address(addr)
                                        ips.add(addr)
                                    except ValueError:
                                        pass
                        return list(ips)
                    except pexpect.exceptions.TIMEOUT:
                        return list(ips)
    finally:
        child.close(force=True)
    return list(ips)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_wait_for_boot():
    """ixnode wait_for_boot() detects the TUI as a booted system."""
    result = _wait_for_boot()
    assert result is True


def test_find_ip_addresses_returns():
    """ixnode _find_ip_addresses() completes without hanging."""
    ips = _find_ip_addresses()
    assert isinstance(ips, list)


def test_find_ip_addresses_extracts_ip():
    """_find_ip_addresses() extracts the IP from the URL banner."""
    ips = _find_ip_addresses()
    assert len(ips) > 0, f"expected at least one IP, got {ips!r}"
    # The mock returns https://192.168.1.108
    assert '192.168.1.108' in ips, f"expected 192.168.1.108 in {ips!r}"


def test_ctrl_d_exits_from_menu():
    """CTRL+D sent after detecting the menu causes clean process exit."""
    child = _spawn()
    try:
        child.expect("Enter an option from 1-", timeout=10)
        child.sendline(CONTROL_D)
        child.expect(pexpect.EOF, timeout=5)
    finally:
        child.close(force=True)


def test_plugin_active_ctrl_d_still_exits():
    """CTRL+D exits cleanly even when a plugin is open (key '1' activated it)."""
    child = _spawn()
    try:
        child.expect("Enter an option from 1-", timeout=10)
        child.send('1')
        child.sendline(CONTROL_D)
        child.expect(pexpect.EOF, timeout=5)
    finally:
        child.close(force=True)


TESTS = [
    test_wait_for_boot,
    test_find_ip_addresses_returns,
    test_find_ip_addresses_extracts_ip,
    test_ctrl_d_exits_from_menu,
    test_plugin_active_ctrl_d_still_exits,
]


def main():
    passed = failed = 0
    for test in TESTS:
        name = test.__name__
        try:
            test()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}")
            print(f"        {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed", end='')
    if failed:
        print(f"  ({failed} FAILED)")
        return 1
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
