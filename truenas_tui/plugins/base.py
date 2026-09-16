"""
Base class for all TUI plugins (menu items).

Each plugin lives under truenas_tui/plugins/<name>/ and must contain:
  view.py        – subclass of BasePlugin
  localization.py – plugin-specific gettext setup

Class attributes:
  REQUIRED_WRITE_ROLES : frozenset[str]
      Middleware RBAC roles needed to make changes via this plugin.
      Empty frozenset means write access is open to all authenticated users.
      Non-empty: plugin may surface a read-only view when the user
      lacks these roles.  The API enforces the actual permissions;
      this is a hint for the UI only.

  LOCAL_ONLY : bool
      When True the plugin is hidden when the session uses a remote
      TCP connection (session.config.server is set).  Defaults False.

  LABEL : str
      Menu label (may be overridden dynamically via get_label()).
  DESCRIPTION : str
      Multi-line description shown in the right pane.
  REFRESH_INTERVAL : int
      Seconds between automatic label refreshes triggered by the main
      view's tick loop.  0 (default) means never auto-refresh.
"""

import time


def _identity(s: str) -> str:
    return s


class BasePlugin:
    REQUIRED_WRITE_ROLES: frozenset[str] = frozenset()
    LOCAL_ONLY: bool = False  # hide when session is remote (config.server set)
    LEGACY_INDEX: int | None = None  # position in --menu (None = not in legacy menu)
    LEGACY_ONLY: bool = False  # if True, hidden in default mode
    DEFAULT_HIDDEN: bool = False  # if True, hidden from default-mode main menu
    LABEL: str = ""
    DESCRIPTION: str = ""
    REFRESH_INTERVAL: int = 0  # seconds; 0 = never auto-refresh
    # Subclasses set this to their domain's TRANSLATE so labels/descriptions
    # are re-translated on every call (locale may change between sessions).
    _TRANSLATE = staticmethod(_identity)

    def can_activate(self, roles: set[str], session=None) -> bool:
        """Return True if the user's roles permit showing this plugin."""
        if self.LOCAL_ONLY and session is not None and session.config.server:
            return False
        return True

    def can_write(self, roles: set[str]) -> bool:
        """Return True if the user's roles permit making changes via this plugin.

        When REQUIRED_WRITE_ROLES is empty, write access is granted to all
        authenticated users.
        """
        if not self.REQUIRED_WRITE_ROLES:
            return True
        return bool(self.REQUIRED_WRITE_ROLES & roles)

    def get_label(self, session) -> str:
        """Return the translated menu label.

        The result is cached per-locale: the cache is busted automatically
        when the active language changes.  Subclasses that need a dynamic
        label (e.g. fetched from the API) should override _fetch_label().
        """
        from truenas_tui import localization  # noqa: PLC0415

        lang = localization._language
        if not hasattr(self, "_label_cache") or self._label_lang != lang:
            self._label_cache = self._fetch_label(session)
            self._label_lang = lang
        return self._label_cache

    def _fetch_label(self, session) -> str:
        """Override to compute a dynamic label (e.g. from an API call)."""
        return self._TRANSLATE(self.LABEL)

    def refresh(self, session) -> None:
        """Bust the label cache and record the refresh timestamp."""
        if hasattr(self, "_label_cache"):
            del self._label_cache
        self._last_refresh = time.monotonic()

    def needs_refresh(self) -> bool:
        """Return True when REFRESH_INTERVAL seconds have elapsed since last refresh."""
        if self.REFRESH_INTERVAL <= 0:
            return False
        return (
            time.monotonic() - getattr(self, "_last_refresh", 0)
            >= self.REFRESH_INTERVAL
        )

    def get_description(self) -> str:
        return self._TRANSLATE(self.DESCRIPTION)

    def run(self, stdscr, session) -> None:
        """
        Take over the screen and implement the plugin's functionality.
        Must restore the terminal state before returning.
        """
        raise NotImplementedError
