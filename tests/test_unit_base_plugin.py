"""BasePlugin: can_write, get_label and get_description.  No curses or network."""

import pytest

from truenas_tui.localization import setup_locale
from truenas_tui.plugins.base import BasePlugin


def _plugin(**attrs):
    """Construct a minimal concrete BasePlugin subclass instance."""
    body = {"REQUIRED_WRITE_ROLES": frozenset(), "LABEL": "Test", "DESCRIPTION": ""}
    body.update(attrs)
    return type("P", (BasePlugin,), body)()


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


class TestLabels:
    def test_get_label_returns_label(self):
        assert _plugin(LABEL="My Label").get_label(None) == "My Label"

    def test_get_label_is_translated(self):
        setup_locale("fr")
        try:
            assert _plugin(LABEL="Error").get_label(None) != "Error"
        finally:
            setup_locale("en")

    def test_get_description_returns_description(self):
        p = _plugin(DESCRIPTION="Some multi-line\ndescription.")
        assert p.get_description() == "Some multi-line\ndescription."

    def test_get_description_empty(self):
        assert _plugin(DESCRIPTION="").get_description() == ""

    def test_run_is_abstract(self):
        with pytest.raises(NotImplementedError):
            _plugin().run(None, None)
