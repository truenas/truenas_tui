"""Unit tests for truenas_tui/tui_preferences.py."""

from truenas_tui.tui_preferences import (
    LANGUAGES,
    TUI_PREFERENCES_KEY,
    VALID_STARTUP_VIEWS,
    VALID_THEMES,
    DateFormat,
    TimeFormat,
    TuiPreferences,
)


def test_preferences_key_value():
    assert TUI_PREFERENCES_KEY == "tui_preferences"


def test_valid_themes_contains_expected():
    assert "default" in VALID_THEMES
    assert "dark" in VALID_THEMES
    assert "high_contrast" in VALID_THEMES


def test_valid_themes_size():
    assert len(VALID_THEMES) == 3


def test_valid_startup_views_contains_expected():
    assert "sysinfo" in VALID_STARTUP_VIEWS
    assert "menu" in VALID_STARTUP_VIEWS


def test_valid_startup_views_size():
    assert len(VALID_STARTUP_VIEWS) == 2


def test_date_format_enum_has_eight_values():
    assert len(DateFormat) == 8


def test_date_format_enum_iso_value():
    assert DateFormat.ISO == "yyyy-MM-dd"


def test_time_format_enum_has_three_values():
    assert len(TimeFormat) == 3


def test_time_format_enum_h24_value():
    assert TimeFormat.H24 == "HH:mm:ss"


def test_languages_contains_english():
    assert "en" in LANGUAGES
    assert LANGUAGES["en"] == "English"


def test_languages_count():
    assert len(LANGUAGES) == 77


def test_default_language():
    assert TuiPreferences().language == "en"


def test_default_date_format():
    assert TuiPreferences().date_format == "yyyy-MM-dd"


def test_default_time_format():
    assert TuiPreferences().time_format == "HH:mm:ss"


def test_default_theme():
    assert TuiPreferences().theme == "default"


def test_default_confirm_dangerous():
    assert TuiPreferences().confirm_dangerous is True


def test_default_startup_view():
    assert TuiPreferences().startup_view == "sysinfo"


def test_to_dict_key_set():
    d = TuiPreferences().to_dict()
    assert set(d.keys()) == {
        "language",
        "date_format",
        "time_format",
        "theme",
        "confirm_dangerous",
        "startup_view",
    }


def test_to_dict_round_trip():
    original = TuiPreferences(
        language="fr",
        date_format=DateFormat.SLASH_US,  # 'MM/dd/yyyy'
        time_format=TimeFormat.H12_AP,  # 'hh:mm:ss aa'
        theme="dark",
        confirm_dangerous=False,
        startup_view="menu",
    )
    restored = TuiPreferences.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_valid():
    d = {
        "language": "de",
        "date_format": "dd.MM.yyyy",  # DateFormat.DOT_EU
        "time_format": "HH:mm:ss",  # TimeFormat.H24
        "theme": "dark",
        "confirm_dangerous": False,
        "startup_view": "menu",
    }
    p = TuiPreferences.from_dict(d)
    assert p.language == "de"
    assert p.date_format == "dd.MM.yyyy"
    assert p.time_format == "HH:mm:ss"
    assert p.theme == "dark"
    assert p.confirm_dangerous is False
    assert p.startup_view == "menu"


def test_from_dict_invalid_theme_falls_back_to_default():
    p = TuiPreferences.from_dict({"theme": "neon_rainbow"})
    assert p.theme == "default"


def test_from_dict_invalid_startup_view_falls_back_to_sysinfo():
    p = TuiPreferences.from_dict({"startup_view": "dashboard"})
    assert p.startup_view == "sysinfo"


def test_from_dict_invalid_date_format_falls_back_to_iso():
    p = TuiPreferences.from_dict({"date_format": "DD.MM.YYYY"})
    assert p.date_format == DateFormat.ISO


def test_from_dict_invalid_time_format_falls_back_to_h24():
    p = TuiPreferences.from_dict({"time_format": "h:mm a"})
    assert p.time_format == TimeFormat.H24


def test_from_dict_invalid_language_falls_back_to_en():
    p = TuiPreferences.from_dict({"language": "xx_FAKE"})
    assert p.language == "en"


def test_from_dict_none_language_collapses():
    p = TuiPreferences.from_dict({"language": None})
    assert p.language == "en"
    assert p.language != "None"


def test_from_dict_none_date_format_collapses():
    p = TuiPreferences.from_dict({"date_format": None})
    assert p.date_format == "yyyy-MM-dd"


def test_from_dict_none_time_format_collapses():
    p = TuiPreferences.from_dict({"time_format": None})
    assert p.time_format == "HH:mm:ss"


def test_from_dict_none_theme_collapses():
    p = TuiPreferences.from_dict({"theme": None})
    assert p.theme == "default"


def test_from_dict_none_startup_view_collapses():
    p = TuiPreferences.from_dict({"startup_view": None})
    assert p.startup_view == "sysinfo"


def test_from_dict_ignores_unknown_keys():
    p = TuiPreferences.from_dict({"unknown_key": "value", "future_field": 42})
    # Should not raise and should return defaults
    assert p.language == "en"
    assert p.theme == "default"


def test_from_dict_empty_dict():
    p = TuiPreferences.from_dict({})
    assert p == TuiPreferences()


def test_confirm_dangerous_truthy_values():
    assert TuiPreferences.from_dict({"confirm_dangerous": 1}).confirm_dangerous is True
    assert (
        TuiPreferences.from_dict({"confirm_dangerous": "yes"}).confirm_dangerous is True
    )
    assert (
        TuiPreferences.from_dict({"confirm_dangerous": True}).confirm_dangerous is True
    )


def test_confirm_dangerous_falsy_values():
    assert TuiPreferences.from_dict({"confirm_dangerous": 0}).confirm_dangerous is False
    assert (
        TuiPreferences.from_dict({"confirm_dangerous": False}).confirm_dangerous
        is False
    )
    assert (
        TuiPreferences.from_dict({"confirm_dangerous": ""}).confirm_dangerous is False
    )
