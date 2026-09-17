#!/usr/bin/env python3
"""
Keep truenas_tui/i18n/<lang>.json in step with the source strings.

    python3 i18n/update_translations.py [--lang fr] [--delay 0.15]

Requires: pip install deep-translator

Removes keys no longer used in the source and machine-translates missing
strings via Google Translate.  Existing entries are never modified.
"""

import argparse
import ast
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).parent.parent
SRC_DIR = ROOT / "truenas_tui"
I18N_DIR = SRC_DIR / "i18n"

# Maps TUI language codes to Google Translate codes.
# Missing from map = pass through as-is.
_GOOGLE_LANG_MAP: dict[str, str] = {
    # Regional / script variants → parent language code
    "zh-hans": "zh-CN",
    "zh-hant": "zh-TW",
    "pt-br": "pt",
    "sr-latn": "sr",
    "es-ar": "es",
    "es-co": "es",
    "es-mx": "es",
    "es-ni": "es",
    "es-ve": "es",
    "nb": "no",
    "nn": "no",
    # Google uses legacy code 'iw' for Hebrew
    "he": "iw",
}


def extract_strings(py_file: pathlib.Path) -> set[str]:
    """TRANSLATE('literal') arguments plus class-level LABEL/DESCRIPTION literals."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(py_file.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "TRANSLATE"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                    and stmt.value.value
                ):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) and t.id in ("LABEL", "DESCRIPTION"):
                            found.add(stmt.value.value)
                            break
    return found


def all_source_strings() -> set[str]:
    strings: set[str] = set()
    for f in SRC_DIR.rglob("*.py"):
        strings |= extract_strings(f)
    return strings


def is_clean(value: str) -> bool:
    """A usable translation: non-empty and free of HTML/Angular syntax."""
    if not value or not value.strip():
        return False
    for c in ("<", ">", "{{"):
        if c in value:
            return False
    return True


def _google_translator() -> Any:
    try:
        from deep_translator import GoogleTranslator  # noqa: PLC0415
    except ImportError:
        sys.exit("deep-translator not installed. Run: pip install deep-translator")
    return GoogleTranslator


def _write(json_file: pathlib.Path, data: dict[str, str]) -> None:
    json_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update(lang_filter: str | None, delay: float) -> None:
    strings = all_source_strings()
    to_translate: list[tuple[pathlib.Path, dict[str, str], list[str]]] = []

    # Stale keys are removed first and need no network access.
    for json_file in sorted(I18N_DIR.glob("*.json")):
        lang = json_file.stem
        if lang_filter and lang != lang_filter:
            continue
        data: dict[str, str] = json.loads(json_file.read_text(encoding="utf-8"))
        stale = []
        for k in data:
            if k not in strings:
                stale.append(k)
        for k in stale:
            del data[k]
        if stale:
            _write(json_file, data)
        missing = []
        for s in strings:
            if not data.get(s):
                missing.append(s)
        missing.sort()
        print(f"  {lang}: {len(stale)} stale removed, {len(missing)} missing")
        if missing:
            to_translate.append((json_file, data, missing))

    if not to_translate:
        return
    GoogleTranslator = _google_translator()
    for json_file, data, missing in to_translate:
        lang = json_file.stem
        print(f"  {lang}: translating {len(missing)} strings", flush=True)
        target = _GOOGLE_LANG_MAP.get(lang, lang)
        try:
            results = GoogleTranslator(source="en", target=target).translate_batch(
                missing
            )
        except Exception as exc:
            print(f"  {lang}: ERROR {exc}", file=sys.stderr, flush=True)
            continue
        for key, result in zip(missing, results):
            if result and is_clean(result):
                if key.endswith("\n") and not result.endswith("\n"):
                    result += "\n"
                data[key] = result
        _write(json_file, data)
        time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--lang", metavar="CODE", help="Limit to one language code (e.g. fr)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        metavar="SECS",
        help="Sleep between languages (default: 0.15)",
    )
    args = parser.parse_args()
    update(args.lang, args.delay)


if __name__ == "__main__":
    main()
