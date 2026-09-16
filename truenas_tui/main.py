"""
truenas-tui entry point.

Usage::

    truenas-tui [--config /path/to/config.conf] [--menu]

If --config is not specified the default path is used:
    ~/.config/truenas_tui.conf

If that file does not exist (or the [truenas] section has no 'server' key)
the client will attempt a local AF_UNIX connection to the middleware socket.

--menu enables the legacy midcli-compatible numbered menu mode (items 1-10,
number-key shortcuts, footer "Enter an option from 1-10:").  Without --menu
the cleaner default mode is used (arrow keys + Enter, no number labels).
"""

import argparse
import curses
import sys

from .api_methods import Method
from .config import Config
from .session import Session
from .tui import HardExit
from .tui.colors import init_colors
from .tui.main_view import MainView

# Plugin registry – order determines default-mode display order.
# Legacy-only plugins appear last (they are hidden in default mode).
from .plugins.network.view import NetworkPlugin
from .plugins.network_interface.view import NetworkInterfacePlugin
from .plugins.network_settings.view import NetworkSettingsPlugin
from .plugins.static_routes.view import StaticRoutesPlugin
from .plugins.my_account.view import MyAccountPlugin
from .plugins.onetime_password.view import OnetimePasswordPlugin
from .plugins.power_control.view import PowerControlPlugin
from .plugins.tui_settings.view import TuiSettingsPlugin
from .plugins.legacy_password.view import PasswordPlugin
from .plugins.legacy_reset_config.view import ResetConfigPlugin
from .plugins.legacy_cli_shell.view import CliShellPlugin
from .plugins.legacy_linux_shell.view import LinuxShellPlugin
from .plugins.legacy_reboot.view import RebootPlugin
from .plugins.legacy_shutdown.view import ShutdownPlugin

ALL_PLUGINS = [
    NetworkPlugin,  # default only (sub-menu wrapping the 3 network plugins)
    MyAccountPlugin,  # default only
    PowerControlPlugin,  # default only
    NetworkInterfacePlugin,  # LEGACY_INDEX=1, DEFAULT_HIDDEN=True
    NetworkSettingsPlugin,  # LEGACY_INDEX=2, DEFAULT_HIDDEN=True
    StaticRoutesPlugin,  # LEGACY_INDEX=3, DEFAULT_HIDDEN=True
    TuiSettingsPlugin,  # DEFAULT_HIDDEN=True (hotkey 's' only)
    OnetimePasswordPlugin,  # LEGACY_INDEX=5, LEGACY_ONLY=True
    PasswordPlugin,  # LEGACY_INDEX=4, LEGACY_ONLY=True
    ResetConfigPlugin,  # LEGACY_INDEX=6, LEGACY_ONLY=True
    CliShellPlugin,  # LEGACY_INDEX=7, LEGACY_ONLY=True, LOCAL_ONLY=True
    LinuxShellPlugin,  # LEGACY_INDEX=8, LEGACY_ONLY=True, LOCAL_ONLY=True
    RebootPlugin,  # LEGACY_INDEX=9, LEGACY_ONLY=True
    ShutdownPlugin,  # LEGACY_INDEX=10, LEGACY_ONLY=True
]


def _print_ui_urls(session) -> None:
    """
    Print web UI URLs to stdout BEFORE entering curses.

    This output is required by ixnode/expect.py's _find_ip_addresses()
    which scans the console byte stream for "The web user interface is at:"
    followed by http/https URLs to extract the server IP.  Without this
    plain-text banner the expect script cannot detect the server address.

    Tries system.general.get_ui_urls first; falls back to constructing
    https:// URLs from active INET interface addresses if that call is
    denied or unavailable.
    """
    urls = []
    if session.config.server:
        # Remote connection: system.general.get_ui_urls is a private method
        # unavailable on the public WebSocket API.  Construct from config.
        urls = [f"https://{session.config.server}"]
    else:
        # Local AF_UNIX: private API is allowed, try get_ui_urls first.
        try:
            urls = session.call(Method.SYSTEM_GENERAL_GET_UI_URLS) or []
        except Exception:
            pass
        if not urls:
            # Fallback: derive URLs from active interface IP addresses.
            try:
                ifaces = session.call(Method.INTERFACE_QUERY)
                for iface in ifaces:
                    for alias in (iface.get("state") or {}).get("aliases", []):
                        if alias.get("type") == "INET":
                            urls.append(f"https://{alias['address']}")
            except Exception:
                pass

    print()
    if urls:
        print("The web user interface is at:")
        for url in urls:
            print(url)
    else:
        print("The web interface could not be accessed.")
        print("Please check network configuration.")
    print()
    sys.stdout.flush()


def _parse_args():
    parser = argparse.ArgumentParser(
        description="TrueNAS Terminal User Interface",
    )
    parser.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        default=None,
        help="Path to config file (default: ~/.config/truenas_tui.conf)",
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Legacy midcli-compatible numbered menu mode",
    )
    return parser.parse_args()


def _tui_main(stdscr, session: Session, menu_mode: bool = False) -> None:
    """Called by curses.wrapper after the terminal is initialised."""
    init_colors(session.tui_prefs.theme)

    user_roles = session.roles
    if menu_mode:
        ordered = sorted(
            [cls for cls in ALL_PLUGINS if cls.LEGACY_INDEX is not None],
            key=lambda cls: cls.LEGACY_INDEX,
        )
    else:
        ordered = [
            cls for cls in ALL_PLUGINS if not cls.LEGACY_ONLY and not cls.DEFAULT_HIDDEN
        ]

    plugins = [
        p for p in (cls() for cls in ordered) if p.can_activate(user_roles, session)
    ]

    if not plugins:
        stdscr.addstr(0, 0, "No accessible menu items for your role.")
        stdscr.refresh()
        stdscr.getch()
        return

    view = MainView(stdscr, session, plugins, menu_mode=menu_mode)
    view.run()


def main() -> None:
    args = _parse_args()
    config = Config(args.config)
    session = Session(config)

    try:
        session.connect()
    except FileNotFoundError:
        if config.server is None:
            print(
                "Error: cannot find the local TrueNAS middleware socket.\n"
                "\n"
                "If you are not running this on a TrueNAS system, supply a\n"
                "config file with the remote server address:\n"
                "\n"
                "    truenas-tui --config /path/to/config.conf\n"
                "\n"
                "Config file format (~/.config/truenas_tui.conf):\n"
                "\n"
                "    [truenas]\n"
                "    server       = 192.168.1.108\n"
                "    username     = admin\n"
                "    api_key_path = /path/to/api.key\n"
                "    verify_ssl   = true\n",
                file=sys.stderr,
            )
        else:
            print(
                f"Failed to connect to {config.server}: connection refused.",
                file=sys.stderr,
            )
        sys.exit(1)
    except Exception as e:
        print(f"Failed to connect to TrueNAS: {e}", file=sys.stderr)
        sys.exit(1)

    _print_ui_urls(session)

    try:
        curses.wrapper(_tui_main, session, args.menu)
    except HardExit:
        pass  # Ctrl+D hard exit – clean termination
    finally:
        session.close()


if __name__ == "__main__":
    main()
