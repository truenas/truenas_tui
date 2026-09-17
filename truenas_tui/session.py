"""
TrueNAS session management.

Handles:
- Connecting via AF_UNIX (local) or wss:// (remote, always api/current)
- auth.me → user info, privilege roles, UI locale preference
- Locale initialisation via localization.setup_locale()
"""

from dataclasses import asdict
import errno
import threading
import time

from truenas_api_client import Client
from truenas_api_client.exc import ClientException

from .localization import setup_locale
from .tui_preferences import TUI_PREFERENCES_KEY, TuiPreferences

_KEEPALIVE_INTERVAL = 5  # seconds of idle before sending core.ping


class Session:
    """
    Maintains a single long-lived API client connection for the TUI.

    Attributes
    ----------
    me          : dict           – full auth.me response
    system_info : dict           – full system.info response
    tui_prefs   : TuiPreferences – per-user TUI preferences
    """

    def __init__(self, config):
        self.config = config
        self._client: Client | None = None
        self.me: dict = {}
        self.system_info: dict = {}
        self.tui_prefs = TuiPreferences()
        self._last_call_time: float = 0.0
        self._reconnect_lock = threading.Lock()
        self._reconnect_generation: int = 0
        self._keepalive_stop = threading.Event()

    def connect(self) -> None:
        """Open the client connection, authenticate, and fetch metadata."""
        self._last_call_time = time.monotonic()
        if self.config.server:
            self._connect_remote(self.config)
            self._start_keepalive()
        else:
            self._connect_local()
        self._fetch_metadata()

    def _connect_remote(self, cfg) -> None:
        url = f"wss://{cfg.server}/api/current"
        self._client = Client(url, verify_ssl=cfg.verify_ssl)
        self._client.__enter__()
        self._client.login_with_api_key(cfg.username, cfg.get_api_key())

    def _connect_local(self) -> None:
        self._client = Client()
        self._client.__enter__()

    def _start_keepalive(self) -> None:
        """Launch the background thread that pings when the connection is idle."""
        self._keepalive_stop.clear()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def _keepalive_loop(self) -> None:
        """Send core.ping every _KEEPALIVE_INTERVAL seconds of inactivity."""
        while not self._keepalive_stop.wait(1.0):
            if time.monotonic() - self._last_call_time >= _KEEPALIVE_INTERVAL:
                try:
                    self.call("core.ping")
                except Exception:
                    pass  # reconnect (if needed) is handled inside call()

    def _reconnect(self, failed_generation: int) -> None:
        """Re-establish the remote connection if the generation hasn't changed."""
        with self._reconnect_lock:
            if self._reconnect_generation != failed_generation:
                return  # another thread already reconnected
            old = self._client
            try:
                old.__exit__(None, None, None)
            except Exception:
                pass
            self._connect_remote(self.config)  # sets self._client on success
            self._reconnect_generation += 1
            self._last_call_time = time.monotonic()

    def _fetch_metadata(self) -> None:
        """Populate me, system_info, preferences and locale."""
        self.me = self._client.call("auth.me")
        self.system_info = self._client.call("system.info")

        # Enforce minimum privilege: READONLY_ADMIN (or a superset thereof).
        # FULL_ADMIN and SHARING_ADMIN both include all READ roles; any of the
        # three is sufficient.  Users with only granular roles (e.g. a custom
        # API key with a single write role) are not supported by this TUI.
        required = {"FULL_ADMIN", "SHARING_ADMIN", "READONLY_ADMIN"}
        roles = self.roles
        if not (roles & required):
            raise PermissionError(
                f"Insufficient privileges.  This TUI requires at least "
                f"READONLY_ADMIN (or FULL_ADMIN / SHARING_ADMIN).  "
                f"Current roles: {', '.join(sorted(roles)) or 'none'}"
            )

        attrs = self.me.get("attributes", {})
        stored = attrs.get(TUI_PREFERENCES_KEY)
        if stored is None:
            # First run: seed the language from the Web UI preference, then persist.
            web_prefs = attrs.get("preferences", {})
            self.tui_prefs = TuiPreferences.from_dict(
                {"language": web_prefs.get("language")}
            )
            try:
                self._client.call(
                    "auth.set_attribute", TUI_PREFERENCES_KEY, asdict(self.tui_prefs)
                )
            except Exception:
                pass  # non-fatal; prefs live in-memory only this session
        else:
            self.tui_prefs = TuiPreferences.from_dict(stored)

        setup_locale(self.tui_prefs.language)

    def close(self) -> None:
        self._keepalive_stop.set()
        if self._client is not None:
            try:
                self._client.__exit__(None, None, None)
            except Exception:
                pass
            self._client = None

    def call(self, method: str, *args, **kwargs):
        """Delegate an API call; reconnect once on connection-aborted errors."""
        self._last_call_time = time.monotonic()
        gen = self._reconnect_generation
        try:
            return self._client.call(method, *args, **kwargs)
        except ClientException as e:
            if e.errno == errno.ECONNABORTED and self.config.server:
                self._reconnect(gen)
                self._last_call_time = time.monotonic()
                return self._client.call(method, *args, **kwargs)
            raise

    @property
    def username(self) -> str:
        return self.me.get("pw_name", "unknown")

    @property
    def roles(self) -> set[str]:
        """Roles from auth.me, which the API delivers as a JSON list."""
        return set(self.me.get("privilege", {}).get("roles") or ())

    @property
    def role_label(self) -> str:
        roles = self.roles
        for label in ("FULL_ADMIN", "SHARING_ADMIN", "READONLY_ADMIN"):
            if label in roles:
                return label
        return "CUSTOM"

    @property
    def hostname(self) -> str:
        return self.system_info.get("hostname", "unknown")

    @property
    def version(self) -> str:
        return self.system_info.get("version", "unknown")
