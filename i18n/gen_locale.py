#!/usr/bin/env python3
"""
TrueNAS TUI locale generator.

Default mode — run during debian package build:
    python3 i18n/gen_locale.py

    Reads i18n/<lang>.json files, generates per-domain .po + .mo files into
    truenas_tui/locale/<lang>/LC_MESSAGES/.

Update-JSON mode — after adding a new plugin:
    python3 i18n/gen_locale.py --update-json [--lang fr] [--delay 0.15]

    Requires: pip install deep-translator

    Finds TRANSLATE() strings not yet present as keys in i18n/<lang>.json,
    machine-translates them via Google Translate, and inserts them.
    Existing entries are never modified.  Writes JSON only — no .po/.mo.
"""
import argparse
import ast
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).parent.parent
LOCALE_DIR = ROOT / 'truenas_tui' / 'locale'
I18N_DIR = ROOT / 'i18n'
SRC_DIR = ROOT / 'truenas_tui'
DOMAINS_FILE = LOCALE_DIR / 'DOMAINS'


# ---------------------------------------------------------------------------
# Domain → source file mapping
# ---------------------------------------------------------------------------

def read_domains() -> list[str]:
    return [d.strip() for d in DOMAINS_FILE.read_text().splitlines() if d.strip()]


def find_domain_sources() -> dict[str, list[pathlib.Path]]:
    """Return {domain: [source_files]} by convention.

    - 'truenas_tui' (core domain) → tui/*.py and any top-level truenas_tui/*.py
      that import TRANSLATE from localization directly.
    - '<domain>' → plugins/<domain>/**/*.py
    """
    domain_sources: dict[str, list[pathlib.Path]] = {}

    core_files: list[pathlib.Path] = []
    for py_file in (SRC_DIR / 'tui').glob('*.py'):
        core_files.append(py_file)
    for py_file in SRC_DIR.glob('*.py'):
        text = py_file.read_text(encoding='utf-8')
        if re.search(r'from\s+truenas_tui\.localization\s+import\s+.*TRANSLATE', text):
            core_files.append(py_file)
    domain_sources['truenas_tui'] = core_files

    plugins_dir = SRC_DIR / 'plugins'
    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir() or plugin_dir.name.startswith('_'):
            continue
        domain = plugin_dir.name
        py_files = list(plugin_dir.rglob('*.py'))
        if py_files:
            domain_sources[domain] = py_files

    return domain_sources


# ---------------------------------------------------------------------------
# AST-based string extraction
# ---------------------------------------------------------------------------

def extract_translate_strings(py_file: pathlib.Path) -> list[str]:
    """Extract translatable strings via AST.

    Picks up:
      - TRANSLATE('literal') calls anywhere in the file
      - LABEL = 'literal' and DESCRIPTION = 'literal' assignments inside class
        bodies (plugins store the raw msgid there for runtime translation via
        _TRANSLATE)
    """
    try:
        tree = ast.parse(py_file.read_text(encoding='utf-8'))
    except SyntaxError:
        return []
    results = []
    for node in ast.walk(tree):
        # TRANSLATE('literal') calls
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'TRANSLATE'
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            results.append(node.args[0].value)
        # class-level LABEL / DESCRIPTION = 'literal'
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                if not any(isinstance(t, ast.Name) and t.id in ('LABEL', 'DESCRIPTION')
                           for t in stmt.targets):
                    continue
                value = stmt.value
                # unwrap bare parentheses: ('string') parses as a Constant
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
                    results.append(value.value)
                # multi-line concatenation: ('a\n' 'b\n') parses as JoinedStr or implicit concat → Constant
                # implicit string concat is folded by the parser into a single Constant, handled above
    return results


def extract_all_translate_strings() -> tuple[set[str], dict[str, set[str]]]:
    """Return (all_strings, {domain: strings}) across the whole source tree."""
    all_strings: set[str] = set()
    domain_strings: dict[str, set[str]] = {}
    for domain, files in find_domain_sources().items():
        strings: set[str] = set()
        for f in files:
            strings.update(extract_translate_strings(f))
        domain_strings[domain] = strings
        all_strings.update(strings)
    return all_strings, domain_strings


# ---------------------------------------------------------------------------
# Translation quality check
# ---------------------------------------------------------------------------

def is_clean_translation(value: str) -> bool:
    """Return True if *value* is a usable translation (not HTML/Angular syntax)."""
    if not value or not value.strip():
        return False
    if any(c in value for c in ('<', '>', '{{')):
        return False
    return True


# ---------------------------------------------------------------------------
# New-format read/write helpers
# ---------------------------------------------------------------------------

def _get_translation(entry) -> str:
    """Extract translation string from either old (str) or new (dict) format."""
    if isinstance(entry, dict):
        return entry.get("translation", "")
    return entry  # backwards-compat during migration


def _make_entry(translation: str, machine_translated: bool) -> dict:
    return {"machine_translated": machine_translated, "translation": translation}


# ---------------------------------------------------------------------------
# .po file generation helpers
# ---------------------------------------------------------------------------

_PO_HEADER = '''\
# TrueNAS TUI - {domain} - {lang}
# Auto-generated by i18n/gen_locale.py — do not edit manually.
#
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Language: {lang}\\n"

'''


def _escape_po(s: str) -> str:
    """Escape a string for use as a .po msgid/msgstr value."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n"\n"')
    return s


def _po_entry(msgid: str, msgstr: str) -> str:
    return f'msgid "{_escape_po(msgid)}"\nmsgstr "{_escape_po(msgstr)}"\n\n'


# ---------------------------------------------------------------------------
# Default mode: generate .po/.mo
# ---------------------------------------------------------------------------

def generate_locale(i18n_dir: pathlib.Path = I18N_DIR,
                    locale_dir: pathlib.Path = LOCALE_DIR) -> None:
    domains = read_domains()
    _all_strings, domain_strings = extract_all_translate_strings()

    json_files = sorted(i18n_dir.glob('*.json'))
    if not json_files:
        print(f'No JSON files found in {i18n_dir}', file=sys.stderr)
        sys.exit(1)

    total_translated = 0
    total_untranslated = 0
    msgfmt_missing = False

    for json_file in json_files:
        lang = json_file.stem
        data: dict = json.loads(json_file.read_text(encoding='utf-8'))

        for domain in domains:
            strings = domain_strings.get(domain, set())
            if not strings:
                continue

            lang_dir = locale_dir / lang / 'LC_MESSAGES'
            lang_dir.mkdir(parents=True, exist_ok=True)

            po_path = lang_dir / f'{domain}.po'
            mo_path = lang_dir / f'{domain}.mo'

            po_content = _PO_HEADER.format(domain=domain, lang=lang)
            for string in sorted(strings):
                entry = data.get(string, {})
                raw = _get_translation(entry)
                msgstr = raw if is_clean_translation(raw) else ''
                # Preserve trailing newline structure so msgfmt doesn't complain
                if msgstr and string.endswith('\n') and not msgstr.endswith('\n'):
                    msgstr += '\n'
                if msgstr:
                    total_translated += 1
                else:
                    total_untranslated += 1
                po_content += _po_entry(string, msgstr)

            po_path.write_text(po_content, encoding='utf-8')

            if not msgfmt_missing:
                result = subprocess.run(
                    ['msgfmt', '-o', str(mo_path), str(po_path)],
                    capture_output=True,
                )
                if result.returncode != 0:
                    print(f'WARNING: msgfmt failed: {result.stderr.decode().strip()}',
                          file=sys.stderr)
                    msgfmt_missing = True

    total = total_translated + total_untranslated
    print(
        f'Generated: {len(json_files)} languages, {len(domains)} domains, '
        f'{len(_all_strings)} strings — '
        f'{total_translated}/{total} translated entries'
        + (' (msgfmt unavailable, .po only)' if msgfmt_missing else '')
    )


# ---------------------------------------------------------------------------
# --update-json mode: machine-translate missing keys into all JSON files
# ---------------------------------------------------------------------------

# Maps TUI language codes to Google Translate codes.
# None = not supported (skip). Missing from map = pass through as-is.
_GOOGLE_LANG_MAP: dict[str, str] = {
    # Regional / script variants → parent language code
    "zh-hans": "zh-CN",
    "zh-hant": "zh-TW",
    "pt-br":   "pt",
    "sr-latn": "sr",
    "es-ar":   "es",
    "es-co":   "es",
    "es-mx":   "es",
    "es-ni":   "es",
    "es-ve":   "es",
    "nb":      "no",
    "nn":      "no",
    # Google uses legacy code 'iw' for Hebrew
    "he":      "iw",
}


def update_json(i18n_dir: pathlib.Path = I18N_DIR,
                lang_filter: str | None = None,
                delay: float = 0.15) -> None:
    """Sync i18n/<lang>.json with current source strings:
      - Remove stale keys no longer referenced in source
      - Machine-translate and insert any missing/empty entries
    """
    try:
        from deep_translator import GoogleTranslator  # noqa: PLC0415
    except ImportError:
        print('ERROR: deep-translator not installed. Run: pip install deep-translator',
              file=sys.stderr)
        sys.exit(1)

    all_strings, _ = extract_all_translate_strings()

    json_files = sorted(i18n_dir.glob('*.json'))
    if not json_files:
        print(f'No JSON files found in {i18n_dir}', file=sys.stderr)
        sys.exit(1)

    for json_file in json_files:
        lang = json_file.stem

        if lang_filter and lang != lang_filter:
            continue

        gt_code = _GOOGLE_LANG_MAP.get(lang, lang)

        data: dict = json.loads(json_file.read_text(encoding='utf-8'))

        # Remove stale keys
        stale = [k for k in data if k not in all_strings]
        for k in stale:
            del data[k]

        missing = [s for s in sorted(all_strings)
                   if not _get_translation(data.get(s, {}))]

        if not missing and not stale:
            print(f'  {lang}: nothing to do')
            continue

        if stale and not missing:
            json_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            print(f'  {lang}: removed {len(stale)} stale entries', flush=True)
            continue

        translator = GoogleTranslator(source='en', target=gt_code)
        inserted = 0
        failed = 0

        for attempt in range(2):
            print(f'  {lang} ({gt_code}): translating {len(missing)} strings'
                  + (f' (retry {attempt})' if attempt else '') + '…', flush=True)
            try:
                results = translator.translate_batch(missing)
                for key, result in zip(missing, results):
                    if result and is_clean_translation(result):
                        data[key] = _make_entry(result, machine_translated=True)
                        inserted += 1
                    else:
                        data[key] = _make_entry('', machine_translated=False)
                        failed += 1
                break
            except Exception as exc:
                print(f'    ERROR: {exc}', file=sys.stderr, flush=True)
                if attempt == 0:
                    time.sleep(delay * 4)
                else:
                    for key in missing:
                        data[key] = _make_entry('', machine_translated=False)
                    failed += len(missing)

        if delay > 0:
            time.sleep(delay)

        json_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        stale_msg = f', {len(stale)} removed' if stale else ''
        print(f'  {lang}: done — {inserted} inserted, {failed} failed{stale_msg}', flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='TrueNAS TUI locale generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--update-json', action='store_true',
        help='Machine-translate missing keys into all i18n JSON files (no .po/.mo written)',
    )
    parser.add_argument(
        '--lang', metavar='CODE',
        help='Limit --update-json to one language code (e.g. fr)',
    )
    parser.add_argument(
        '--delay', type=float, default=0.15, metavar='SECS',
        help='Sleep between translation requests for --update-json (default: 0.15)',
    )
    parser.add_argument(
        '--i18n-dir', metavar='PATH', default=str(I18N_DIR),
        help=f'i18n JSON directory (default: {I18N_DIR})',
    )
    args = parser.parse_args()

    i18n_dir = pathlib.Path(args.i18n_dir)

    if args.update_json:
        print('Inserting missing translations into JSON files…')
        update_json(i18n_dir=i18n_dir, lang_filter=args.lang, delay=args.delay)
        print('Done.')
    else:
        print('Generating .po/.mo files…')
        generate_locale(i18n_dir=i18n_dir)


if __name__ == '__main__':
    main()
