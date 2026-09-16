"""
Group 1 – Internal Logic: BasePlugin class.

Covers can_activate, can_write, get_label caching, refresh, needs_refresh,
and get_description.  No curses or network required.
"""

from unittest.mock import patch

import pytest

from truenas_tui.plugins.base import BasePlugin


def _plugin(**attrs):
    """Construct a minimal concrete BasePlugin subclass instance."""
    return type(
        "P",
        (BasePlugin,),
        {
            "REQUIRED_WRITE_ROLES": attrs.get("REQUIRED_WRITE_ROLES", frozenset()),
            "LOCAL_ONLY": attrs.get("LOCAL_ONLY", False),
            "LABEL": attrs.get("LABEL", "Test"),
            "DESCRIPTION": attrs.get("DESCRIPTION", ""),
            "REFRESH_INTERVAL": attrs.get("REFRESH_INTERVAL", 0),
        },
    )()


def _session(server="host"):
    """Minimal session-like object with a config.server attribute."""

    class Cfg:
        pass

    class Sess:
        config = Cfg()

    s = Sess()
    s.config.server = server
    return s


class TestCanActivate:
    def test_can_activate_non_local_always_true(self):
        p = _plugin(LOCAL_ONLY=False)
        assert p.can_activate(set()) is True

    def test_can_activate_non_local_any_roles_true(self):
        p = _plugin(LOCAL_ONLY=False)
        assert p.can_activate({"SOME_ROLE"}) is True

    def test_local_only_hidden_when_server_set(self):
        p = _plugin(LOCAL_ONLY=True)
        assert p.can_activate(set(), _session(server="192.168.1.1")) is False

    def test_local_only_visible_when_server_none(self):
        p = _plugin(LOCAL_ONLY=True)
        assert p.can_activate(set(), _session(server=None)) is True

    def test_local_only_no_session_arg_defaults_true(self):
        p = _plugin(LOCAL_ONLY=True)
        assert p.can_activate(set()) is True

    def test_local_only_explicit_none_session(self):
        p = _plugin(LOCAL_ONLY=True)
        assert p.can_activate(set(), session=None) is True


class TestCanWrite:
    def test_no_required_write_roles_always_true(self):
        p = _plugin(REQUIRED_WRITE_ROLES=frozenset())
        assert p.can_write(set()) is True

    def test_write_role_match(self):
        p = _plugin(REQUIRED_WRITE_ROLES=frozenset({"W"}))
        assert p.can_write({"W", "R"}) is True

    def test_write_role_mismatch(self):
        p = _plugin(REQUIRED_WRITE_ROLES=frozenset({"W"}))
        assert p.can_write({"R"}) is False

    def test_write_role_empty_user_roles(self):
        p = _plugin(REQUIRED_WRITE_ROLES=frozenset({"W"}))
        assert p.can_write(set()) is False

    def test_required_write_roles_is_frozenset(self):
        p = _plugin()
        assert isinstance(p.REQUIRED_WRITE_ROLES, frozenset)

    def test_required_write_roles_is_immutable(self):
        p = _plugin()
        with pytest.raises(AttributeError):
            p.REQUIRED_WRITE_ROLES.add("X")


class TestGetLabel:
    def test_returns_label_class_attr(self):
        p = _plugin(LABEL="My Label")
        assert p.get_label(None) == "My Label"

    def test_result_cached_on_second_call(self):
        calls = []

        class TrackPlugin(BasePlugin):
            LABEL = "Base"

            def _fetch_label(self, session):
                calls.append(1)
                return "Fetched"

        p = TrackPlugin()
        p.get_label(None)
        p.get_label(None)
        assert len(calls) == 1

    def test_refresh_busts_cache(self):
        calls = []

        class TrackPlugin(BasePlugin):
            LABEL = "Base"

            def _fetch_label(self, session):
                calls.append(1)
                return "Fetched"

        p = TrackPlugin()
        p.get_label(None)
        p.refresh(None)
        p.get_label(None)
        assert len(calls) == 2

    def test_fetch_label_default_returns_label(self):
        p = _plugin(LABEL="Direct")
        # _fetch_label is not overridden; should return LABEL
        assert p._fetch_label(None) == "Direct"


class TestNeedsRefresh:
    def test_zero_interval_never_needs_refresh(self):
        p = _plugin(REFRESH_INTERVAL=0)
        assert p.needs_refresh() is False

    def test_zero_interval_after_refresh_still_false(self):
        p = _plugin(REFRESH_INTERVAL=0)
        p.refresh(None)
        assert p.needs_refresh() is False

    def test_positive_interval_before_elapsed_false(self):
        p = _plugin(REFRESH_INTERVAL=60)
        p.refresh(None)
        assert p.needs_refresh() is False

    def test_positive_interval_never_refreshed_true(self):
        # _last_refresh defaults to 0 via getattr(..., 0);
        # time.monotonic() is always >> 1 second, so this is True.
        p = _plugin(REFRESH_INTERVAL=1)
        assert p.needs_refresh() is True

    def test_positive_interval_after_elapsed_true(self):
        p = _plugin(REFRESH_INTERVAL=1)
        # Fake time: refresh records t=0.0, needs_refresh sees t=2.0
        with patch("truenas_tui.plugins.base.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 2.0]
            p.refresh(None)
            assert p.needs_refresh() is True

    def test_positive_interval_before_elapsed_false_mocked(self):
        p = _plugin(REFRESH_INTERVAL=60)
        with patch("truenas_tui.plugins.base.time") as mock_time:
            mock_time.monotonic.side_effect = [100.0, 110.0]
            p.refresh(None)  # _last_refresh = 100.0
            assert p.needs_refresh() is False  # 110.0 - 100.0 = 10 < 60


def test_get_description_returns_description():
    p = _plugin(DESCRIPTION="Some multi-line\ndescription.")
    assert p.get_description() == "Some multi-line\ndescription."


def test_get_description_empty():
    p = _plugin(DESCRIPTION="")
    assert p.get_description() == ""
