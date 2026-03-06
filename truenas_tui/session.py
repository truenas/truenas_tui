"""
TrueNAS session management.

Handles:
- Connecting via AF_UNIX (local) or wss:// (remote, always api/current)
- API version detection from GET /api/versions (remote) or system.info (local)
- auth.me → user info, privilege roles, UI locale preference
- Locale initialisation via localization.setup_locale()
"""
import errno
import threading
import time
import urllib.request
import json
import re
import ssl

from truenas_api_client import Client
from truenas_api_client.exc import ClientException

from .api_methods import Method
from .localization import setup_locale
from .tui_preferences import TuiPreferences, TUI_PREFERENCES_KEY


_KEEPALIVE_INTERVAL = 5   # seconds of idle before sending core.ping


def _parse_version(ver: str) -> tuple[int, ...]:
    """
    Convert a version string like 'v25.10.0' or '25.10.0' into a comparable
    integer tuple (25, 10, 0).
    """
    ver = ver.lstrip('v')
    parts = re.split(r'[.\-]', ver)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    # Pad to at least 3 elements
    while len(result) < 3:
        result.append(0)
    return tuple(result)


def _make_ssl_context(verify_ssl: bool, ca_cert: str | None) -> ssl.SSLContext:
    """
    Build an SSLContext for the REST /api/versions call.

    verify_ssl=True  → full certificate + hostname verification (default).
    verify_ssl=False → verification disabled (only for self-signed certs).
    ca_cert          → path to a PEM CA bundle to use instead of the system store.
    """
    if verify_ssl:
        ctx = ssl.create_default_context()
        if ca_cert:
            ctx.load_verify_locations(ca_cert)
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Session:
    """
    Maintains a single long-lived API client connection for the TUI.

    Attributes
    ----------
    me              : dict           – full auth.me response
    system_info     : dict           – full system.info response
    api_version     : tuple          – e.g. (25, 10, 0) – latest version server supports
    api_versions    : list           – all supported version tuples, newest last
    tui_prefs       : TuiPreferences – per-user TUI preferences
    date_format     : str            – delegated to tui_prefs.date_format (property)
    time_format     : str            – delegated to tui_prefs.time_format (property)
    """

    def __init__(self, config):
        self.config = config
        self._client: Client | None = None
        self.me: dict = {}
        self.system_info: dict = {}
        self.api_version: tuple[int, ...] = (0, 0, 0)
        self.api_versions: list[tuple[int, ...]] = []
        self.tui_prefs: TuiPreferences = TuiPreferences()
        self._last_call_time: float = 0.0
        self._reconnect_lock = threading.Lock()
        self._reconnect_generation: int = 0
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the client connection, authenticate, and fetch metadata."""
        cfg = self.config
        self._last_call_time = time.monotonic()
        if cfg.server:
            self._connect_remote(cfg)
            self._start_keepalive()
        else:
            self._connect_local()
        self._fetch_metadata()

    def _connect_remote(self, cfg) -> None:
        url = f"wss://{cfg.server}/api/current"
        self._client = Client(url, verify_ssl=cfg.verify_ssl)
        self._client.__enter__()
        key = cfg.get_api_key()
        self._client.login_with_api_key(cfg.username, key)
        self.api_versions = self._fetch_remote_versions(cfg.server, cfg.verify_ssl, cfg.ca_cert)
        if self.api_versions:
            self.api_version = self.api_versions[-1]

    def _connect_local(self) -> None:
        self._client = Client()
        self._client.__enter__()
        # Version will be derived from system.info after _fetch_metadata

    def _start_keepalive(self) -> None:
        """Launch the background thread that pings when the connection is idle."""
        self._keepalive_stop.clear()
        t = threading.Thread(target=self._keepalive_loop, daemon=True)
        t.start()
        self._keepalive_thread = t

    def _keepalive_loop(self) -> None:
        """Send core.ping every _KEEPALIVE_INTERVAL seconds of inactivity."""
        while not self._keepalive_stop.wait(1.0):
            if time.monotonic() - self._last_call_time >= _KEEPALIVE_INTERVAL:
                try:
                    self.call(Method.CORE_PING)
                except Exception:
                    pass   # reconnect (if needed) is handled inside call()

    def _reconnect(self, failed_generation: int) -> None:
        """Re-establish the remote connection if the generation hasn't changed."""
        with self._reconnect_lock:
            if self._reconnect_generation != failed_generation:
                return   # another thread already reconnected
            old = self._client
            try:
                old.__exit__(None, None, None)
            except Exception:
                pass
            self._connect_remote(self.config)   # sets self._client on success
            self._reconnect_generation += 1
            self._last_call_time = time.monotonic()

    def _fetch_remote_versions(
        self, host: str, verify_ssl: bool, ca_cert: str | None
    ) -> list[tuple[int, ...]]:
        """
        GET https://{host}/api/versions and return a sorted list of version
        tuples.  Falls back to an empty list on any error.
        """
        try:
            ctx = _make_ssl_context(verify_ssl, ca_cert)
            req = urllib.request.Request(
                f"https://{host}/api/versions",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                versions_raw: list[str] = json.loads(resp.read())
            versions = sorted(_parse_version(v) for v in versions_raw)
            return versions
        except Exception:
            return []

    def _fetch_metadata(self) -> None:
        """Populate me, system_info, locale, and api_version."""
        self.me = self._client.call(Method.AUTH_ME)
        self.system_info = self._client.call(Method.SYSTEM_INFO)

        # Derive API version from system.info when not set by remote version fetch
        if self.api_version == (0, 0, 0):
            raw = self.system_info.get('version', '')
            self.api_version = _parse_version(raw)
            self.api_versions = [self.api_version]

        # Enforce minimum privilege: READONLY_ADMIN (or a superset thereof).
        # FULL_ADMIN and SHARING_ADMIN both include all READ roles; any of the
        # three is sufficient.  Users with only granular roles (e.g. a custom
        # API key with a single write role) are not supported by this TUI.
        required = {'FULL_ADMIN', 'SHARING_ADMIN', 'READONLY_ADMIN'}
        roles = self.me.get('privilege', {}).get('roles', set())
        if not (roles & required):
            raise PermissionError(
                f'Insufficient privileges.  This TUI requires at least '
                f'READONLY_ADMIN (or FULL_ADMIN / SHARING_ADMIN).  '
                f'Current roles: {", ".join(sorted(roles)) or "none"}'
            )

        attrs   = self.me.get('attributes', {})
        prefs   = attrs.get('preferences', {})
        tui_raw = attrs.get(TUI_PREFERENCES_KEY)

        if tui_raw is None:
            # First run: seed from Web UI prefs, then persist.
            self.tui_prefs = TuiPreferences.from_dict({
                'language':    prefs.get('language',   'en') or 'en',
                'date_format': prefs.get('dateFormat', '')   or '',
                'time_format': prefs.get('timeFormat', '')   or '',
            })
            try:
                self._client.call(
                    Method.AUTH_SET_ATTRIBUTE,
                    TUI_PREFERENCES_KEY, self.tui_prefs.to_dict(),
                )
            except Exception:
                pass   # non-fatal; prefs live in-memory only this session
        else:
            self.tui_prefs = TuiPreferences.from_dict(tui_raw)

        setup_locale(self.tui_prefs.language)

    def close(self) -> None:
        self._keepalive_stop.set()
        if self._client is not None:
            try:
                self._client.__exit__(None, None, None)
            except Exception:
                pass
            self._client = None

    # ------------------------------------------------------------------
    # API proxy
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Convenience properties derived from auth.me / system.info
    # ------------------------------------------------------------------

    @property
    def username(self) -> str:
        return self.me.get('pw_name', 'unknown')

    @property
    def roles(self) -> set[str]:
        return self.me.get('privilege', {}).get('roles', set())

    @property
    def role_label(self) -> str:
        roles = self.roles
        for label in ('FULL_ADMIN', 'SHARING_ADMIN', 'READONLY_ADMIN'):
            if label in roles:
                return label
        return 'CUSTOM'

    @property
    def hostname(self) -> str:
        return self.system_info.get('hostname', 'unknown')

    @property
    def version(self) -> str:
        return self.system_info.get('version', 'unknown')

    def has_role(self, *roles: str) -> bool:
        """Return True if the session has any of the given roles."""
        return bool(self.roles & set(roles))

    @property
    def date_format(self) -> str:
        return self.tui_prefs.date_format

    @date_format.setter
    def date_format(self, value: str) -> None:
        self.tui_prefs.date_format = value

    @property
    def time_format(self) -> str:
        return self.tui_prefs.time_format

    @time_format.setter
    def time_format(self, value: str) -> None:
        self.tui_prefs.time_format = value
