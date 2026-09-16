"""
Unit tests for truenas_tui.localization.

Covers:
  - _LOCALE_DIR exists inside the package
  - setup_locale() clears the translation cache
  - Fallback to English for unknown/invalid language codes
  - _SAFE_LANG_RE accepts valid locale tags, rejects traversal strings
  - All TRANSLATE() string literals in every source file have a key in every i18n JSON
"""

import importlib
import json
import pathlib
import sys

import pytest

# Ensure project root is importable
ROOT = pathlib.Path(__file__).parent.parent
I18N_DIR = ROOT / "i18n"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "i18n"))


def _reload_localization():
    """Re-import localization so we get a fresh module state."""
    import truenas_tui.localization as loc

    importlib.reload(loc)
    return loc


def test_localedir_exists():
    import truenas_tui.localization as loc

    assert loc._LOCALE_DIR.is_dir(), (
        f"_LOCALE_DIR {loc._LOCALE_DIR} does not exist; "
        "run i18n/gen_locale.py to create it"
    )


def test_localedir_is_inside_package():
    import truenas_tui.localization as loc

    pkg_dir = pathlib.Path(loc.__file__).parent
    assert loc._LOCALE_DIR == pkg_dir / "locale"


def test_setup_locale_clears_cache():
    import truenas_tui.localization as loc

    # Warm the cache with at least one domain
    loc.setup_locale("en")
    _ = loc._get("truenas_tui")
    assert loc._cache  # non-empty

    loc.setup_locale("fr")
    assert loc._cache == {}, "setup_locale() should clear the translation cache"


def test_setup_locale_stores_language():
    import truenas_tui.localization as loc

    loc.setup_locale("de")
    assert loc._language == "de"
    loc.setup_locale("en")  # reset


def test_fallback_english_unknown_lang():
    import truenas_tui.localization as loc

    loc.setup_locale("xx_FAKE")
    # Should fall back silently: _language set to 'xx_FAKE' (valid pattern),
    # but gettext fallback=True → returns English msgid unchanged.
    result = loc.TRANSLATE("Network")
    assert isinstance(result, str)
    assert result != ""


def test_fallback_english_invalid_lang_rejected():
    """Invalid/dangerous language codes must be silently replaced with 'en'."""
    import truenas_tui.localization as loc

    for bad in ("../../etc", "", "  ", "en; rm -rf /", "../passwd"):
        loc.setup_locale(bad)
        assert loc._language == "en", (
            f"Expected 'en' for bad lang {bad!r}, got {loc._language!r}"
        )
    loc.setup_locale("en")  # reset


VALID_LANGS = ["en", "fr", "de", "zh-hans", "pt-br", "sr-latn", "zh_CN", "pt_BR"]
INVALID_LANGS = ["../../etc", "", "  ", "en; rm -rf /", "a", "toolongcode"]


@pytest.mark.parametrize("lang", VALID_LANGS)
def test_safe_lang_re_valid(lang):
    import truenas_tui.localization as loc

    assert loc._SAFE_LANG_RE.match(lang), f"Expected {lang!r} to be accepted"


@pytest.mark.parametrize("lang", INVALID_LANGS)
def test_safe_lang_re_rejects(lang):
    import truenas_tui.localization as loc

    assert not loc._SAFE_LANG_RE.match(lang), f"Expected {lang!r} to be rejected"


def _extract_all_translate_strings() -> set[str]:
    """Import gen_locale and extract all TRANSLATE() strings from source."""
    # Dynamically import the build script without installing it
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_locale", ROOT / "i18n" / "gen_locale.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    all_strings, _ = mod.extract_all_translate_strings()
    return all_strings


@pytest.mark.skipif(
    not I18N_DIR.exists() or not list(I18N_DIR.glob("*.json")),
    reason="i18n/*.json files not yet generated (run bootstrap first)",
)
def test_all_translate_strings_have_json_keys():
    """Every TRANSLATE() literal must appear as a key in every i18n JSON file."""
    strings = _extract_all_translate_strings()
    assert strings, "No TRANSLATE() strings found — check source extraction"

    missing_report: list[str] = []
    shape_report: list[str] = []
    for json_path in sorted(I18N_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        missing = [s for s in strings if s not in data]
        if missing:
            sample = missing[:5]
            missing_report.append(
                f"{json_path.name}: {len(missing)} missing keys, e.g. {sample}"
            )
        for key, val in data.items():
            if not isinstance(val, dict):
                shape_report.append(
                    f"{json_path.name}: {key!r} value must be a dict, got {type(val).__name__!r}"
                )
            elif "translation" not in val or "machine_translated" not in val:
                shape_report.append(
                    f"{json_path.name}: {key!r} missing 'translation' or 'machine_translated'"
                )

    assert not missing_report, (
        "Some TRANSLATE() strings are not present as keys in i18n JSON files:\n"
        + "\n".join(missing_report)
    )
    assert not shape_report, (
        "Some i18n JSON values have wrong shape (expected {translation, machine_translated}):\n"
        + "\n".join(shape_report[:20])
    )
