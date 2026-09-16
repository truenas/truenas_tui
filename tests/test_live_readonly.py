#!/usr/bin/env python3
"""
Live read-only integration test against a real TrueNAS server.

Runs the exact same pexpect logic as ixnode/expect.py's
wait_for_boot() and _find_ip_addresses() against the real TUI.

SAFE: only read operations — never activates any plugin.

Usage:
    python3 tests/test_live_readonly.py --config /path/to/config.conf
"""

import argparse
import ipaddress
import os
import sys

import pexpect

CONTROL_D = "\x04"
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable


def _spawn(config_path: str) -> pexpect.spawn:
    return pexpect.spawn(
        PYTHON,
        ["-m", "truenas_tui.main", "--config", config_path],
        timeout=20,
        dimensions=(24, 80),
        cwd=PKG_ROOT,
        env={**os.environ, "TERM": "xterm"},
    )


def wait_for_boot(config_path, timeout=20):
    """Mirrors ixnode/expect.py::wait_for_boot()"""
    child = _spawn(config_path)
    child.sendline()
    index = child.expect(
        ["The web user interface is at", "Enter an option from 1-"],
        timeout=timeout,
    )
    if index in [0, 1]:
        child.close(force=True)
        return True
    child.close(force=True)
    raise TimeoutError("Failed to detect booted TUI")


def _find_ip_addresses(config_path, itimeout=5, timeout=30):
    """Mirrors ixnode/expect.py::_find_ip_addresses()"""
    ips = set()
    child = _spawn(config_path)
    try:
        child.sendline()
        while timeout > 0:
            index = child.expect(
                ["The web user interface is at", "Enter an option from 1-"],
                timeout=itimeout,
            )
            timeout -= itimeout
            if index in [0, 1]:
                if index == 1:
                    child.sendline(CONTROL_D)
                else:
                    try:
                        while child.expect(["http://", "https://"], timeout=1) in [
                            0,
                            1,
                        ]:
                            index = child.expect([":"], timeout=1)
                            timeout -= 2
                            if index == 0:
                                for line in child.before.decode("utf-8").split("\n"):
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


def test_wait_for_boot(config_path):
    """ixnode wait_for_boot() detects our TUI as a booted system."""
    result = wait_for_boot(config_path, timeout=20)
    assert result is True


def test_find_ip_addresses(config_path):
    """ixnode _find_ip_addresses() runs against our TUI without hanging."""
    # We don't assert specific IPs — the TUI doesn't print web UI URLs
    # (unlike midcli), so the list will be empty.  What matters is that
    # the function returns (doesn't time out or crash).
    ips = _find_ip_addresses(config_path, itimeout=5, timeout=30)
    assert isinstance(ips, list)


TESTS = [
    test_wait_for_boot,
    test_find_ip_addresses,
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    passed = failed = 0
    for test in TESTS:
        name = test.__name__
        try:
            test(args.config)
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}")
            print(f"        {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        return 1
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
