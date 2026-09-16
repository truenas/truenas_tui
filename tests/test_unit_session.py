"""Unit tests for truenas_tui/session.py."""

import errno
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from truenas_api_client.exc import ClientException

from truenas_tui.session import Session
from truenas_tui.tui_preferences import TUI_PREFERENCES_KEY, TuiPreferences


class MockConfig:
    server = "192.168.1.108"
    username = "admin"
    verify_ssl = False

    def get_api_key(self):
        return "test-api-key"


class LocalConfig:
    server = None
    username = "root"
    verify_ssl = True

    def get_api_key(self):
        return None


def _make_me(roles=None, language="en", tui_prefs=None):
    attrs = {"preferences": {"language": language}}
    if tui_prefs is not None:
        attrs[TUI_PREFERENCES_KEY] = tui_prefs
    return {
        "pw_name": "admin",
        "privilege": {"roles": set(roles or {"FULL_ADMIN"})},
        "attributes": attrs,
    }


def _make_sysinfo(version="25.10.0", hostname="testnas"):
    return {"version": version, "hostname": hostname}


def test_init_defaults():
    cfg = MockConfig()
    session = Session(cfg)
    assert session.config is cfg
    assert session._client is None
    assert session.me == {}
    assert session.system_info == {}
    assert session.tui_prefs == TuiPreferences()


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

    with patch("truenas_tui.session.Client", return_value=mock_client) as MockClient:
        session._connect_remote(cfg)

    MockClient.assert_called_once_with(
        "wss://192.168.1.108/api/current", verify_ssl=False
    )
    mock_client.__enter__.assert_called_once()
    mock_client.login_with_api_key.assert_called_once_with("admin", "test-api-key")


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


def test_fetch_metadata_sets_attrs():
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="fr")
    sysinfo = _make_sysinfo(version="25.10.0", hostname="nas1")
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: auth.set_attribute
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    assert session.me["pw_name"] == "admin"
    assert session.system_info["hostname"] == "nas1"
    mock_locale.assert_called_once_with("fr")


def test_fetch_metadata_insufficient_role():
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"SOME_CUSTOM_ROLE"})
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo]  # raises before auth.set_attribute
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"), pytest.raises(PermissionError):
        session._fetch_metadata()


def test_fetch_metadata_locale_setup():
    """setup_locale is called with the language from preferences."""
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"READONLY_ADMIN"}, language="de")
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, None]  # 3rd: auth.set_attribute
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    mock_locale.assert_called_once_with("de")


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
    """No tui_preferences key: language seeded from preferences.language and persisted."""
    session = Session(MockConfig())
    mock_client = MagicMock()
    me = _make_me(roles={"FULL_ADMIN"}, language="fr")
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo, None]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale"):
        session._fetch_metadata()

    assert session.tui_prefs.language == "fr"
    assert session.tui_prefs.theme == "default"
    # auth.set_attribute was called (3rd call) with the serialised prefs
    method, key, value = mock_client.call.call_args_list[2][0]
    assert method == "auth.set_attribute"
    assert key == TUI_PREFERENCES_KEY
    assert value == {"language": "fr", "theme": "default", "startup_view": "sysinfo"}


def test_fetch_metadata_first_run_writeback_failure_nonfatal():
    """auth.set_attribute raises; no exception propagated; tui_prefs still set."""
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
    """tui_preferences key present: from_dict used; auth.set_attribute NOT called."""
    stored = {"language": "de", "theme": "dark", "startup_view": "menu"}
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
    # Only 2 calls: auth.me and system.info; no auth.set_attribute
    assert mock_client.call.call_count == 2


def test_fetch_metadata_setup_locale_uses_tui_prefs_language():
    """setup_locale receives tui_prefs.language, not preferences.language."""
    stored = {"language": "zh-hans", "theme": "default", "startup_view": "sysinfo"}
    session = Session(MockConfig())
    mock_client = MagicMock()
    # Web UI prefs say 'en', but tui_prefs stores 'zh-hans'
    me = _make_me(roles={"FULL_ADMIN"}, language="en", tui_prefs=stored)
    sysinfo = _make_sysinfo()
    mock_client.call.side_effect = [me, sysinfo]
    session._client = mock_client

    with patch("truenas_tui.session.setup_locale") as mock_locale:
        session._fetch_metadata()

    mock_locale.assert_called_once_with("zh-hans")


def test_keepalive_starts_on_remote_connect():
    session = Session(MockConfig())
    session._keepalive_stop.set()  # prove connect() clears it
    with (
        patch.object(session, "_connect_remote"),
        patch.object(session, "_fetch_metadata"),
        patch("truenas_tui.session.threading.Thread") as MockThread,
    ):
        session.connect()
    assert not session._keepalive_stop.is_set()
    MockThread.return_value.start.assert_called_once()


def test_keepalive_not_started_for_local():
    session = Session(LocalConfig())
    with (
        patch.object(session, "_connect_local"),
        patch.object(session, "_fetch_metadata"),
        patch("truenas_tui.session.threading.Thread") as MockThread,
    ):
        session.connect()
    MockThread.assert_not_called()


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
    mock_client.call.assert_called_with("core.ping")


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
    mock_client.call.assert_not_called()


def test_close_stops_keepalive():
    session = Session(MockConfig())
    session._client = MagicMock()
    session._start_keepalive()
    assert not session._keepalive_stop.is_set()
    session.close()
    assert session._keepalive_stop.is_set()


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
        result = session.call("system.info")

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
        session.call("system.info")

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
