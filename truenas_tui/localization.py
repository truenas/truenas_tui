"""
Translation lookup.

Each language ships as truenas_tui/i18n/<lang>.json, a flat dict mapping the
English source string to its translation.  setup_locale() loads one language
and TRANSLATE() looks strings up in it, returning the source text when there
is no translation.
"""

import json
import pathlib

I18N_DIR = pathlib.Path(__file__).parent / "i18n"

_table: dict[str, str] = {}


def setup_locale(language: str) -> None:
    """Load translations for *language*; English or an unknown code loads none."""
    global _table
    try:
        path = I18N_DIR / f"{language}.json"
        _table = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _table = {}


def TRANSLATE(message: str) -> str:
    return _table.get(message) or message
