"""
truenas-tui entry point.

Usage::

    truenas-tui [--config /path/to/config.conf] [--menu]

If --config is not specified the default path is used:
    ~/.config/truenas_tui.conf

If that file does not exist (or the [truenas] section has no 'server' key)
the client will attempt a local AF_UNIX connection to the middleware socket.

--menu enables the legacy midcli-compatible numbered menu mode (number-key
shortcuts, footer "Enter an option from 1-N:").  Without --menu the cleaner
default mode is used (arrow keys + Enter, no number labels).
"""

import argparse
import curses
import sys

from .config import Config
from .plugins.base import BasePlugin
from .plugins.legacy_cli_shell.view import CliShellPlugin
from .plugins.legacy_linux_shell.view import LinuxShellPlugin
from .plugins.legacy_password.view import PasswordPlugin
from .plugins.legacy_reboot.view import RebootPlugin
from .plugins.legacy_reset_config.view import ResetConfigPlugin
from .plugins.legacy_shutdown.view import ShutdownPlugin
from .plugins.my_account.view import MyAccountPlugin
from .plugins.network.view import NetworkPlugin
from .plugins.network_interface.view import NetworkInterfacePlugin
from .plugins.network_settings.view import NetworkSettingsPlugin
from .plugins.onetime_password.view import OnetimePasswordPlugin
from .plugins.power_control.view import PowerControlPlugin
from .plugins.static_routes.view import StaticRoutesPlugin
from .session import Session
from .tui import HardExit
from .tui.colors import init_colors
from .tui.main_view import MainView

# Menu contents and order.  In --menu mode an item's number is its position
# in LEGACY_MENU, which mirrors midcli --menu.  TuiSettingsPlugin is in
# neither menu; default mode reaches it with the 's' hotkey.
DEFAULT_MENU: list[type[BasePlugin]] = [
    NetworkPlugin,
    MyAccountPlugin,
    PowerControlPlugin,
]
LEGACY_MENU: list[type[BasePlugin]] = [
    NetworkInterfacePlugin,
    NetworkSettingsPlugin,
    StaticRoutesPlugin,
    PasswordPlugin,
    OnetimePasswordPlugin,
    ResetConfigPlugin,
    CliShellPlugin,
    LinuxShellPlugin,
    RebootPlugin,
    ShutdownPlugin,
]


def menu_plugins(session: Session, menu_mode: bool) -> list[BasePlugin]:
    """Instantiate the menu for this mode, hiding LOCAL_ONLY items on remote sessions."""
    menu = LEGACY_MENU if menu_mode else DEFAULT_MENU
    plugins: list[BasePlugin] = []
    for cls in menu:
        if not (cls.LOCAL_ONLY and session.config.server):
            plugins.append(cls())
    return plugins


def _print_ui_urls(session: Session) -> None:
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
    urls: list[str] = []
    if session.config.server:
        # Remote connection: system.general.get_ui_urls is a private method
        # unavailable on the public WebSocket API.  Construct from config.
        urls = [f"https://{session.config.server}"]
    else:
        # Local AF_UNIX: private API is allowed, try get_ui_urls first.
        try:
            urls = session.call("system.general.get_ui_urls") or []
        except Exception:
            pass
        if not urls:
            # Fallback: derive URLs from active interface IP addresses.
            try:
                ifaces = session.call("interface.query")
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


def _parse_args() -> argparse.Namespace:
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


def _tui_main(stdscr: curses.window, session: Session, menu_mode: bool = False) -> None:
    """Called by curses.wrapper after the terminal is initialised."""
    init_colors(session.tui_prefs.theme)
    MainView(stdscr, session, menu_plugins(session, menu_mode), menu_mode).run()


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
