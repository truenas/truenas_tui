"""
Base class for all TUI plugins (menu items).

Each plugin lives in truenas_tui/plugins/<name>/view.py as a BasePlugin
subclass.  Menu membership and order come from the DEFAULT_MENU and
LEGACY_MENU lists in truenas_tui/main.py.
"""

from truenas_tui.localization import TRANSLATE


class BasePlugin:
    # Middleware RBAC roles needed to make changes through this plugin.  Empty
    # means write access is open to all authenticated users.  The API enforces
    # the real permissions; this only drives the read-only hint in the menu.
    REQUIRED_WRITE_ROLES: frozenset[str] = frozenset()
    LOCAL_ONLY: bool = False  # hide when the session is remote (config.server set)
    LABEL: str = ""  # menu label, translated by get_label()
    DESCRIPTION: str = ""  # multi-line description shown in the right pane

    def can_write(self, roles: set[str]) -> bool:
        """Return True if the user's roles permit making changes via this plugin."""
        return not self.REQUIRED_WRITE_ROLES or bool(self.REQUIRED_WRITE_ROLES & roles)

    def get_label(self, session) -> str:
        return TRANSLATE(self.LABEL)

    def get_description(self) -> str:
        return TRANSLATE(self.DESCRIPTION)

    def run(self, stdscr, session) -> None:
        """
        Take over the screen and implement the plugin's functionality.
        Must restore the terminal state before returning.
        """
        raise NotImplementedError
