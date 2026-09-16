"""Per-user TUI preferences stored under auth.me['attributes']['tui_preferences']."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import StrEnum


class DateFormat(StrEnum):
    """Date format strings matching the TrueNAS WebUI / date-fns conventions."""

    ISO = "yyyy-MM-dd"
    LONG_US = "MMMM d, yyyy"
    LONG_EU = "d MMMM, yyyy"
    SHORT_US = "MMM d, yyyy"
    SHORT_EU = "d MMM yyyy"
    SLASH_US = "MM/dd/yyyy"
    SLASH_EU = "dd/MM/yyyy"
    DOT_EU = "dd.MM.yyyy"


class TimeFormat(StrEnum):
    """Time format strings matching the TrueNAS WebUI / date-fns conventions."""

    H24 = "HH:mm:ss"
    H12_AM = "hh:mm:ss aaaaa'm'"
    H12_AP = "hh:mm:ss aa"


# Language code → display name (matches the TrueNAS WebUI languages constant).
LANGUAGES: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "Deutsch",
    "el": "Greek",
    "en": "English",
    "eo": "Esperanto",
    "es-ar": "Argentinian Spanish",
    "es-co": "Colombian Spanish",
    "es-mx": "Mexican Spanish",
    "es-ni": "Nicaraguan Spanish",
    "es-ve": "Venezuelan Spanish",
    "es": "Español",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "Français",
    "fy": "Frisian",
    "ga": "Irish",
    "gd": "Scottish Gaelic",
    "gl": "Galician",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italiano",
    "ja": "Japanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "lb": "Luxembourgish",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "my": "Burmese",
    "nb": "Norwegian Bokmål",
    "ne": "Nepali",
    "nl": "Dutch",
    "nn": "Norwegian Nynorsk",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt-br": "Brazilian Portuguese",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr-latn": "Serbian Latin",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "tt": "Tatar",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh-hans": "中文",
    "zh-hant": "Traditional Chinese",
}

_DATE_FORMAT_VALUES = frozenset(DateFormat)
_TIME_FORMAT_VALUES = frozenset(TimeFormat)

TUI_PREFERENCES_KEY = "tui_preferences"
VALID_THEMES = frozenset({"default", "dark", "high_contrast"})
VALID_STARTUP_VIEWS = frozenset({"sysinfo", "menu"})


@dataclass
class TuiPreferences:
    language: str = "en"
    date_format: str = DateFormat.ISO
    time_format: str = TimeFormat.H24
    theme: str = "default"
    confirm_dangerous: bool = True
    startup_view: str = "sysinfo"

    @classmethod
    def from_dict(cls, d: dict) -> TuiPreferences:
        """Deserialise, ignoring unknown keys; invalid enum values → defaults."""
        theme = str(d.get("theme", "default") or "default")
        startup_view = str(d.get("startup_view", "sysinfo") or "sysinfo")
        lang_raw = str(d.get("language", "en") or "en")
        date_raw = str(d.get("date_format", "") or "")
        time_raw = str(d.get("time_format", "") or "")
        return cls(
            language=lang_raw if lang_raw in LANGUAGES else "en",
            date_format=date_raw if date_raw in _DATE_FORMAT_VALUES else DateFormat.ISO,
            time_format=time_raw if time_raw in _TIME_FORMAT_VALUES else TimeFormat.H24,
            theme=theme if theme in VALID_THEMES else "default",
            confirm_dangerous=bool(d.get("confirm_dangerous", True)),
            startup_view=startup_view
            if startup_view in VALID_STARTUP_VIEWS
            else "sysinfo",
        )

    def to_dict(self) -> dict:
        return asdict(self)
