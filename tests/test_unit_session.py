"""Unit tests for truenas_tui/session.py."""

import errno
import ssl
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from truenas_api_client.exc import ClientException

from truenas_tui.api_methods import Method
from truenas_tui.session import Session, _make_ssl_context, _parse_version
from truenas_tui.tui_preferences import TUI_PREFERENCES_KEY, TuiPreferences


class MockConfig:
    server = "192.168.1.108"
    username = "admin"
    verify_ssl = False
    ca_cert = None

    def get_api_key(self):
        return "test-api-key"


class LocalConfig:
    server = None
    username = "root"
    verify_ssl = True
    ca_cert = None

    def get_api_key(self):
        return None


def _make_me(roles=None, language="en", tui_prefs=None):
    attrs = {
        "preferences": {
            "language": language,
            "dateFormat": "yyyy-MM-DD",
            "timeFormat": "HH:mm:ss",
        }
    }
    if tui_prefs is not None:
        attrs[TUI_PREFERENCES_KEY] = tui_prefs
    return {
        "pw_name": "admin",
        "privilege": {"roles": set(roles or {"FULL_ADMIN"})},
        "attributes": attrs,
    }


def _make_sysinfo(version="25.10.0", hostname="testnas"):
    return {"version": version, "hostname": hostname}


def test_parse_version_with_v_prefix():
    assert _parse_version("v25.10.0") == (25, 10, 0)


def test_parse_version_no_prefix():
    assert _parse_version("25.10.0") == (25, 10, 0)


def test_parse_version_two_parts():
    # Only two numeric parts → padded to 3
    assert _parse_version("25.10") == (25, 10, 0)


def test_parse_version_with_rc_suffix():
    # Hyphen-split stops at non-numeric; rc1 is ignored
    assert _parse_version("25.10.0-rc1") == (25, 10, 0)


def test_parse_version_one_part():
    assert _parse_version("25") == (25, 0, 0)


def test_parse_version_extra_parts():
    # More than 3 numeric parts kept as-is
    result = _parse_version("25.10.0.1")
    assert result[:3] == (25, 10, 0)


def test_parse_version_non_numeric_start():
    # If first part is non-numeric, result is padded to (0, 0, 0)
    result = _parse_version("TrueNAS-25.10.0")
    # 'TrueNAS' fails int(), loop breaks immediately → []  → (0, 0, 0)
    assert result == (0, 0, 0)


def test_ssl_context_verify_false():
    ctx = _make_ssl_context(verify_ssl=False, ca_cert=None)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_ssl_context_verify_true():
    ctx = _make_ssl_context(verify_ssl=True, ca_cert=None)
    # Should be a valid context with verification enabled
    assert ctx.verify_mode != ssl.CERT_NONE


def test_ssl_context_with_ca_cert():
    """When ca_cert is set, load_verify_locations should be called."""
    with patch("ssl.create_default_context") as mock_factory:
        mock_ctx = MagicMock()
        mock_factory.return_value = mock_ctx
        _make_ssl_context(verify_ssl=True, ca_cert="/path/to/ca.pem")
    mock_ctx.load_verify_locations.assert_called_once_with("/path/to/ca.pem")


def test_init_defaults():
    cfg = MockConfig()
    session = Session(cfg)
    assert session.config is cfg
    assert session._client is None
    assert session.me == {}
    assert session.system_info == {}
    assert session.api_version == (0, 0, 0)
    assert session.api_versions == []
    assert session.tui_prefs == TuiPreferences()
    assert session.date_format == "yyyy-MM-dd"
    assert session.time_format == "HH:mm:ss"


def test_username_from_me():
    session = Session(MockConfig())
    session.me = _make_me()
    assert session.username == "admin"


def test_username_fallback():
    session = Session(MockConfig())
    session.me = {}
    assert session.username == "unknown"


def test_roles_from_me():
    session = Session(MockConfig())
    session.me = _make_me(roles={"FULL_ADMIN", "NETWORK_INTERFACE_READ"})
    assert "FULL_ADMIN" in session.roles
    assert "NETWORK_INTERFACE_READ" in session.roles


def test_roles_empty():
    session = Session(MockConfig())
    session.me = {}
    assert session.roles == set()


def test_role_label_full_admin():
    session = Session(MockConfig())
    session.me = _make_me(roles={"FULL_ADMIN"})
    assert session.role_label == "FULL_ADMIN"


def test_role_label_sharing_admin():
    session = Session(MockConfig())
    session.me = _make_me(roles={"SHARING_ADMIN"})
    assert session.role_label == "SHARING_ADMIN"


def test_role_label_readonly_admin():
    session = Session(MockConfig())
    session.me = _make_me(roles={"READONLY_ADMIN"})
    assert session.role_label == "READONLY_ADMIN"


def test_role_label_custom():
    session = Session(MockConfig())
    session.me = _make_me(roles={"SOME_CUSTOM_ROLE"})
    assert session.role_label == "CUSTOM"


def test_hostname_from_sysinfo():
    session = Session(MockConfig())
    session.system_info = _make_sysinfo(hostname="bobnas")
    assert session.hostname == "bobnas"


def test_hostname_fallback():
    session = Session(MockConfig())
    session.system_info = {}
    assert session.hostname == "unknown"


def test_version_from_sysinfo():
    session = Session(MockConfig())
    session.system_info = _make_sysinfo(version="TrueNAS-25.10.0")
    assert session.version == "TrueNAS-25.10.0"


def test_version_fallback():
    session = Session(MockConfig())
    session.system_info = {}
    assert session.version == "unknown"


def test_has_role_matching():
    session = Session(MockConfig())
    session.me = _make_me(roles={"FULL_ADMIN", "ACCOUNT_READ"})
    assert session.has_role("FULL_ADMIN") is True
    assert session.has_role("ACCOUNT_READ") is True
    assert session.has_role("FULL_ADMIN", "READONLY_ADMIN") is True


def test_has_role_no_match():
    session = Session(MockConfig())
    session.me = _make_me(roles={"READONLY_ADMIN"})
    assert session.has_role("FULL_ADMIN") is False
    assert session.has_role("SHARING_ADMIN") is False


def test_close_exits_client():
    session = Session(MockConfig())
    mock_client = MagicMock()
    session._client = mock_client

    session.close()

    mock_client.__exit__.assert_called_once_with(None, None, None)
    assert session._client is None


def test_close_suppresses_exception():
    session = Session(MockConfig())
    mock_client = MagicMock()
    mock_client.__exit__.side_effect = RuntimeError("network gone")
    session._client = mock_client

    # Should not raise
    session.close()
    assert session._client is None


def test_close_noop_when_no_client():
    session = Session(MockConfig())
    session._client = None
    # Should not raise
    session.close()


def test_connect_remote_creates_client():
    cfg = MockConfig()
    session = Session(cfg)
    mock_client = MagicMock()

    with (
        patch("truenas_tui.session.Client", return_value=mock_client) as MockClient,
        patch.object(
            session, "_fetch_remote_versions", return_value=[(25, 4, 0), (25, 10, 0)]
        ),
    ):
        session._connect_remote(cfg)

    MockClient.assert_called_once_with(
        "wss://192.168.1.108/api/current", verify_ssl=False
    )
    mock_client.__enter__.assert_called_once()
    mock_client.login_with_api_key.assert_called_once_with("admin", "test-api-key")
    assert session.api_versions == [(25, 4, 0), (25, 10, 0)]
    assert session.api_version == (25, 10, 0)


def test_connect_remote_empty_versions():
    """When _fetch_remote_versions returns [], api_version stays at (0, 0, 0)."""
    cfg = MockConfig()
    session = Session(cfg)
    mock_client = MagicMock()

    with (
        patch("truenas_tui.session.Client", return_value=mock_client),
        patch.object(session, "_fetch_remote_versions", return_value=[]),
    ):
        session._connect_remote(cfg)

    assert session.api_version == (0, 0, 0)
    assert session.api_versions == []


def test_connect_local_creates_client():
    cfg = LocalConfig()
    session = Session(cfg)
    mock_client = MagicMock()

    with patch("truenas_tui.session.Client", return_value=mock_client) as MockClient:
        session._connect_local()

    # Called with no args for local AF_UNIX connection
    MockClient.assert_called_once_with()
    mock_client.__enter__.assert_called_once()
    assert session._client is mock_client


def test_fetch_remote_versions_success():
    session = Session(MockConfig())
    raw_json = b'["v25.10.0", "v25.4.0", "v25.4.2"]'

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = raw_json

    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        patch("truenas_tui.session._make_ssl_context", return_value=MagicMock()),
    ):
        versions = session._fetch_remote_versions("192.168.1.108", False, None)

    # Sorted ascending
    assert versions == [(25, 4, 0), (25, 4, 2), (25, 10, 0)]


def test_fetch_remote_versions_network_error():
    session = Session(MockConfig())

    with (
        patch("urllib.request.urlopen", side_effect=OSError("connection refused")),
        patch("truenas_tui.session._make_ssl_context", return_value=MagicMock()),
    ):
        versions = session._fetch_remote_versions("192.168.1.108", False, None)

    assert versions == []


def test_fetch_metadata_sets_attrs():
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="fr")
    sysinfo = _make_sysinfo(version="25.10.0", hostname="nas1")
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: AUTH_SET_ATTRIBUTE
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    assert session.me["pw_name"] == "admin"
    assert session.system_info["hostname"] == "nas1"
    mock_locale.assert_called_once_with("fr")
    # version derived from system_info
    assert session.api_version == (25, 10, 0)


def test_fetch_metadata_insufficient_role():
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"SOME_CUSTOM_ROLE"})
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo]  # raises before AUTH_SET_ATTRIBUTE
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"), pytest.raises(PermissionError):
        session._fetch_metadata()


def test_fetch_metadata_locale_setup():
    """setup_locale is called with the language from preferences."""
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"READONLY_ADMIN"}, language="de")
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: AUTH_SET_ATTRIBUTE
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    mock_locale.assert_called_once_with("de")


def test_fetch_metadata_date_time_formats():
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"})
    me["attributes"]["preferences"]["dateFormat"] = "MM/dd/yyyy"
    me["attributes"]["preferences"]["timeFormat"] = "hh:mm:ss aa"
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: AUTH_SET_ATTRIBUTE
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()

    assert session.date_format == "MM/dd/yyyy"
    assert session.time_format == "hh:mm:ss aa"


def test_fetch_metadata_version_not_overwritten_if_already_set():
    """If api_version was set by remote version fetch, system_info version is not used."""
    session = Session(MockConfig())
    session.api_version = (25, 4, 0)  # already set by _connect_remote
    session.api_versions = [(25, 4, 0)]

    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"})
    sysinfo = _make_sysinfo(version="99.99.99")  # would parse to (99, 99, 99) if used
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: AUTH_SET_ATTRIBUTE
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()

    # api_version should remain what was set before
    assert session.api_version == (25, 4, 0)


def test_call_delegates_to_client():
    session = Session(MockConfig())
    mock_client = MagicMock()
    mock_client.call.return_value = {"result": "ok"}
    session._client = mock_client

    result = session.call("some.method", "arg1", key="val")

    mock_client.call.assert_called_once_with("some.method", "arg1", key="val")
    assert result == {"result": "ok"}


def test_tui_prefs_default_on_init():
    session = Session(MockConfig())
    assert session.tui_prefs == TuiPreferences()


def test_fetch_metadata_first_run_seeds_from_web_prefs():
    """No tui_preferences key: prefs seeded from preferences.language/dateFormat/timeFormat."""
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="fr")
    me["attributes"]["preferences"]["dateFormat"] = "dd/MM/yyyy"
    me["attributes"]["preferences"]["timeFormat"] = "HH:mm:ss"
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, None]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()

    assert session.tui_prefs.language == "fr"
    assert session.tui_prefs.date_format == "dd/MM/yyyy"
    assert session.tui_prefs.time_format == "HH:mm:ss"
    # AUTH_SET_ATTRIBUTE was called (3rd call)
    calls = mock_client.call.call_args_list
    assert calls[2][0][0] == Method.AUTH_SET_ATTRIBUTE


def test_fetch_metadata_first_run_writeback_failure_nonfatal():
    """AUTH_SET_ATTRIBUTE raises; no exception propagated; tui_prefs still set."""
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="en")
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, RuntimeError("API error")]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()  # must not raise

    assert session.tui_prefs.language == "en"


def test_fetch_metadata_existing_tui_prefs_deserialized():
    """tui_preferences key present: from_dict used; AUTH_SET_ATTRIBUTE NOT called."""
    stored = {
        "language": "de",
        "date_format": "dd.MM.yyyy",
        "time_format": "HH:mm:ss",
        "theme": "dark",
        "confirm_dangerous": False,
        "startup_view": "menu",
    }
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="en", tui_prefs=stored)
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()

    assert session.tui_prefs.language == "de"
    assert session.tui_prefs.theme == "dark"
    assert session.tui_prefs.startup_view == "menu"
    # Only 2 calls: AUTH_ME and SYSTEM_INFO; no AUTH_SET_ATTRIBUTE
    assert mock_client.call.call_count == 2


def test_fetch_metadata_setup_locale_uses_tui_prefs_language():
    """setup_locale receives tui_prefs.language, not preferences.language."""
    stored = {
        "language": "zh-hans",
        "date_format": "yyyy-MM-dd",
        "time_format": "HH:mm:ss",
        "theme": "default",
        "confirm_dangerous": True,
        "startup_view": "sysinfo",
    }
    session = Session(MockConfig())
    mock_client = MagicMock()
    # Web UI prefs say 'en', but tui_prefs stores 'zh_CN'
    me = _make_me(roles={"FULL_ADMIN"}, language="en", tui_prefs=stored)
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    mock_locale.assert_called_once_with("zh-hans")


def test_date_format_property_delegates_to_tui_prefs():
    session = Session(MockConfig())
    session.tui_prefs = TuiPreferences(date_format="MM/dd/yyyy")
    assert session.date_format == "MM/dd/yyyy"
    session.date_format = "dd/MM/yyyy"
    assert session.tui_prefs.date_format == "dd/MM/yyyy"


def test_time_format_property_delegates_to_tui_prefs():
    session = Session(MockConfig())
    session.tui_prefs = TuiPreferences(time_format="hh:mm:ss aa")
    assert session.time_format == "hh:mm:ss aa"
    session.time_format = "hh:mm:ss aaaaa'm'"
    assert session.tui_prefs.time_format == "hh:mm:ss aaaaa'm'"


def test_keepalive_thread_starts_on_remote_connect():
    session = Session(MockConfig())
    with (
        patch.object(session, "_connect_remote"),
        patch.object(session, "_fetch_metadata"),
    ):
        session.connect()
    try:
        assert session._keepalive_thread is not None
        assert session._keepalive_thread.is_alive()
    finally:
        session._keepalive_stop.set()
        session._keepalive_thread.join(timeout=2.0)


def test_keepalive_thread_not_started_for_local():
    session = Session(LocalConfig())
    with (
        patch.object(session, "_connect_local"),
        patch.object(session, "_fetch_metadata"),
    ):
        session.connect()
    assert session._keepalive_thread is None


def test_keepalive_sends_ping_when_idle():
    session = Session(MockConfig())
    mock_client = MagicMock()
    mock_client.call.return_value = "pong"
    session._client = mock_client
    # Simulate >5 s of inactivity
    session._last_call_time = time.monotonic() - 10.0
    session._start_keepalive()
    try:
        time.sleep(1.5)
    finally:
        session._keepalive_stop.set()
        session._keepalive_thread.join(timeout=2.0)
    mock_client.call.assert_called_with(Method.CORE_PING)


def test_keepalive_skips_ping_when_recent_activity():
    session = Session(MockConfig())
    mock_client = MagicMock()
    session._client = mock_client
    # Fresh activity — should not ping within the next second
    session._last_call_time = time.monotonic()
    session._start_keepalive()
    try:
        time.sleep(1.5)
    finally:
        session._keepalive_stop.set()
        session._keepalive_thread.join(timeout=2.0)
    mock_client.call.assert_not_called()


def test_close_stops_keepalive_thread():
    session = Session(MockConfig())
    session._client = MagicMock()
    session._start_keepalive()
    assert session._keepalive_thread.is_alive()
    session.close()
    assert session._keepalive_stop.is_set()
    session._keepalive_thread.join(timeout=2.0)
    assert not session._keepalive_thread.is_alive()


def test_call_reconnects_on_econnaborted():
    session = Session(MockConfig())

    first_client = MagicMock()
    first_client.call.side_effect = ClientException(
        "connection aborted", errno.ECONNABORTED
    )
    session._client = first_client

    second_client = MagicMock()
    second_client.call.return_value = {"result": "ok"}

    def fake_connect_remote(cfg):
        session._client = second_client

    with patch.object(session, "_connect_remote", side_effect=fake_connect_remote):
        result = session.call(Method.SYSTEM_INFO)

    assert result == {"result": "ok"}
    assert session._reconnect_generation == 1


def test_call_does_not_reconnect_for_local():
    session = Session(LocalConfig())  # config.server is None
    mock_client = MagicMock()
    mock_client.call.side_effect = ClientException(
        "connection aborted", errno.ECONNABORTED
    )
    session._client = mock_client

    with pytest.raises(ClientException):
        session.call(Method.SYSTEM_INFO)

    assert session._reconnect_generation == 0


def test_reconnect_generation_prevents_double_reconnect():
    session = Session(MockConfig())
    session._client = MagicMock()

    connect_count = [0]

    def fake_connect_remote(cfg):
        connect_count[0] += 1
        session._client = MagicMock()

    errors = []

    def reconnect_thread():
        try:
            session._reconnect(0)
        except Exception as e:
            errors.append(e)

    with patch.object(session, "_connect_remote", side_effect=fake_connect_remote):
        t1 = threading.Thread(target=reconnect_thread)
        t2 = threading.Thread(target=reconnect_thread)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

    assert not errors
    assert connect_count[0] == 1
    assert session._reconnect_generation == 1
