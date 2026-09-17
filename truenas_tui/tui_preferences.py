"""Per-user TUI preferences stored under auth.me['attributes']['tui_preferences']."""

from __future__ import annotations

from collections.abc import Container
from dataclasses import dataclass
from typing import Any

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

TUI_PREFERENCES_KEY = "tui_preferences"
VALID_THEMES = frozenset({"default", "dark", "high_contrast"})
VALID_STARTUP_VIEWS = frozenset({"sysinfo", "menu"})


def _pick(value: object, allowed: Container[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


@dataclass(slots=True, kw_only=True, frozen=True)
class TuiPreferences:
    language: str = "en"
    theme: str = "default"
    startup_view: str = "sysinfo"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuiPreferences:
        """Deserialise, ignoring unknown keys; invalid values fall back to defaults."""
        return cls(
            language=_pick(d.get("language"), LANGUAGES, "en"),
            theme=_pick(d.get("theme"), VALID_THEMES, "default"),
            startup_view=_pick(d.get("startup_view"), VALID_STARTUP_VIEWS, "sysinfo"),
        )
