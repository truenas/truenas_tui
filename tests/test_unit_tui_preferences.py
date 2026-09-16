"""Unit tests for truenas_tui/tui_preferences.py."""

from dataclasses import asdict

from truenas_tui.tui_preferences import (
    LANGUAGES,
    TUI_PREFERENCES_KEY,
    VALID_STARTUP_VIEWS,
    VALID_THEMES,
    TuiPreferences,
)


def test_preferences_key_value():
    assert TUI_PREFERENCES_KEY == "tui_preferences"


def test_valid_themes():
    assert VALID_THEMES == {"default", "dark", "high_contrast"}


def test_valid_startup_views():
    assert VALID_STARTUP_VIEWS == {"sysinfo", "menu"}


def test_languages_contains_english():
    assert LANGUAGES["en"] == "English"


def test_languages_count():
    assert len(LANGUAGES) == 77


def test_defaults():
    assert TuiPreferences() == TuiPreferences(
        language="en", theme="default", startup_view="sysinfo"
    )


def test_asdict_key_set():
    assert set(asdict(TuiPreferences())) == {"language", "theme", "startup_view"}


def test_asdict_round_trip():
    original = TuiPreferences(language="fr", theme="dark", startup_view="menu")
    assert TuiPreferences.from_dict(asdict(original)) == original


def test_from_dict_valid():
    p = TuiPreferences.from_dict(
        {"language": "de", "theme": "dark", "startup_view": "menu"}
    )
    assert p.language == "de"
    assert p.theme == "dark"
    assert p.startup_view == "menu"


def test_from_dict_invalid_theme_falls_back_to_default():
    assert TuiPreferences.from_dict({"theme": "neon_rainbow"}).theme == "default"


def test_from_dict_invalid_startup_view_falls_back_to_sysinfo():
    p = TuiPreferences.from_dict({"startup_view": "dashboard"})
    assert p.startup_view == "sysinfo"


def test_from_dict_invalid_language_falls_back_to_en():
    assert TuiPreferences.from_dict({"language": "xx_FAKE"}).language == "en"


def test_from_dict_none_values_collapse():
    p = TuiPreferences.from_dict(
        {"language": None, "theme": None, "startup_view": None}
    )
    assert p == TuiPreferences()


def test_from_dict_non_string_values_collapse():
    p = TuiPreferences.from_dict({"language": ["fr"], "theme": 3})
    assert p == TuiPreferences()


def test_from_dict_ignores_unknown_keys():
    p = TuiPreferences.from_dict({"unknown_key": "value", "future_field": 42})
    assert p == TuiPreferences()


def test_from_dict_empty_dict():
    assert TuiPreferences.from_dict({}) == TuiPreferences()
