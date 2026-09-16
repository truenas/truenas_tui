"""
Unit tests for truenas_tui.localization.

Covers:
  - I18N_DIR lives inside the package
  - setup_locale() loads a language table and falls back for unknown codes
  - TRANSLATE() returns the translation or the source string
  - Language files contain only current source strings
"""

import importlib.util
import json
import pathlib

import pytest

import truenas_tui.localization as loc

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _reset_locale():
    yield
    loc.setup_locale("en")


def test_i18n_dir_is_inside_package():
    assert loc.I18N_DIR == pathlib.Path(loc.__file__).parent / "i18n"
    assert loc.I18N_DIR.is_dir()


def test_english_loads_no_table():
    loc.setup_locale("en")
    assert loc._table == {}
    assert loc.TRANSLATE("Error") == "Error"


def test_translation_lookup():
    loc.setup_locale("fr")
    assert loc._table
    assert loc.TRANSLATE("Error") == loc._table["Error"]
    assert loc.TRANSLATE("Error") != "Error"


def test_missing_key_falls_back_to_source():
    loc.setup_locale("fr")
    assert loc.TRANSLATE("no such string") == "no such string"


@pytest.mark.parametrize("bad", ["xx_FAKE", "../../etc", "", "  "])
def test_unknown_language_falls_back(bad):
    loc.setup_locale("fr")
    loc.setup_locale(bad)
    assert loc._table == {}
    assert loc.TRANSLATE("Error") == "Error"


def _all_source_strings() -> set[str]:
    """Load the translation script by path and extract every source string."""
    spec = importlib.util.spec_from_file_location(
        "update_translations", ROOT / "i18n" / "update_translations.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.all_source_strings()


def test_language_files_match_source_strings():
    """Language files hold only current source strings, as non-empty text.

    A string with no entry falls back to English, so missing translations are
    allowed; i18n/update_translations.py fills them in and removes stale keys.
    """
    strings = _all_source_strings()
    assert strings, "No translatable strings found — check source extraction"

    report: list[str] = []
    for json_path in sorted(loc.I18N_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        bad = [k for k, v in data.items() if not isinstance(v, str) or not v]
        if bad:
            report.append(f"{json_path.name}: non-string values for {bad[:5]}")
        stale = sorted(k for k in data if k not in strings)
        if stale:
            report.append(
                f"{json_path.name}: {len(stale)} stale keys, e.g. {stale[:5]}"
            )
    assert not report, (
        "Run i18n/update_translations.py to bring the language files up to date:\n"
        + "\n".join(report)
    )
