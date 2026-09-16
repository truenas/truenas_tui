#!/usr/bin/env python3
"""
Runs the TUI with the MockSession backend.

Invoke directly:
    python3 tests/run_mock_tui.py [--local] [--menu]

Flags:
    --local   Set session.config.server = None so LOCAL_ONLY plugins appear
              (CliShell, LinuxShell).  Default is remote mode (server set).
    --menu    Enable legacy midcli-compatible numbered menu mode (items 1-10,
              number-key shortcuts, footer "Enter an option from 1-10:").
              Without this flag the default mode is used (arrow keys only).

Used by test_expect_compat.py and E2E tests as the subprocess target.
"""

import argparse
import curses
import os
import sys

# Ensure the package root is on the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mock_session import MockSession
from truenas_tui.localization import setup_locale
from truenas_tui.main import ALL_PLUGINS, _print_ui_urls
from truenas_tui.tui import HardExit
from truenas_tui.tui.colors import init_colors
from truenas_tui.tui.main_view import MainView


def _tui_main(stdscr, session, menu_mode: bool = False):
    init_colors()
    if menu_mode:
        ordered = sorted(
            [cls for cls in ALL_PLUGINS if cls.LEGACY_INDEX is not None],
            key=lambda cls: cls.LEGACY_INDEX,
        )
    else:
        ordered = [cls for cls in ALL_PLUGINS if not cls.LEGACY_ONLY]
    plugins = [
        p for p in (cls() for cls in ordered) if p.can_activate(session.roles, session)
    ]
    view = MainView(stdscr, session, plugins, menu_mode=menu_mode)
    view.run()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run with server=None to show LOCAL_ONLY plugins",
    )
    parser.add_argument(
        "--menu", action="store_true", help="Enable legacy numbered menu mode"
    )
    args = parser.parse_args()

    setup_locale("en")
    session = MockSession()
    if args.local:
        session.config.server = None  # instance attr shadows class attr

    _print_ui_urls(session)
    try:
        curses.wrapper(_tui_main, session, args.menu)
    except HardExit:
        pass
    finally:
        session.close()


if __name__ == "__main__":
    main()
