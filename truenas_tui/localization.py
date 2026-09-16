"""
Localization support.

All locale files live under truenas_tui/locale/<lang>/LC_MESSAGES/<domain>.mo.
Each component (core, plugins) has its own domain so it can be translated
independently.

Usage in any module::

    from truenas_tui.localization import make_translator
    TRANSLATE, ngettext = make_translator('network_settings')

After auth.me is resolved, call setup_locale() once with the user's
preferred language code (e.g. 'en', 'fr').  The translation cache is
cleared so all subsequent TRANSLATE() calls use the new language.
"""

import gettext
import pathlib
import re

_LOCALE_DIR = pathlib.Path(__file__).parent / "locale"

_language: str = "en"
_cache: dict[str, gettext.NullTranslations] = {}

# Accept only well-formed locale tags: "en", "fr", "zh_CN", "pt_BR", etc.
# Rejects path traversal strings like "../../etc/passwd".
_SAFE_LANG_RE = re.compile(r"^[a-zA-Z]{2,3}([_\-][a-zA-Z]{2,4})?$")


def setup_locale(language: str) -> None:
    """Switch all domains to *language* (e.g. 'en', 'fr', 'de').

    The language code is validated against a strict allowlist pattern before
    use.  An invalid or missing code silently falls back to 'en', preventing
    path-traversal attacks via a malicious auth.me response.
    """
    global _language
    lang = language or "en"
    if not _SAFE_LANG_RE.match(lang):
        lang = "en"
    _language = lang
    _cache.clear()


def _get(domain: str) -> gettext.NullTranslations:
    if domain not in _cache:
        _cache[domain] = gettext.translation(
            domain,
            localedir=str(_LOCALE_DIR),
            languages=[_language],
            fallback=True,
        )
    return _cache[domain]


def make_translator(domain: str):
    """
    Return (TRANSLATE, ngettext) callables bound to *domain*.

    Because lookups go through _get() they automatically pick up the
    current language even if setup_locale() is called after the module
    is imported.
    """

    def TRANSLATE(message: str) -> str:
        return _get(domain).gettext(message)

    def ngettext(singular: str, plural: str, n: int) -> str:
        return _get(domain).ngettext(singular, plural, n)

    return TRANSLATE, ngettext


# Core / main domain used by tui/ and main.py
TRANSLATE, ngettext = make_translator("truenas_tui")
