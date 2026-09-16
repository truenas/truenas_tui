from dataclasses import asdict

from truenas_tui.localization import TRANSLATE, setup_locale
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.colors import init_colors
from truenas_tui.tui.dialogs import message_dialog
from truenas_tui.tui.forms import ChoiceField, Form, SectionField
from truenas_tui.tui_preferences import (
    LANGUAGES,
    TUI_PREFERENCES_KEY,
    VALID_STARTUP_VIEWS,
    VALID_THEMES,
    TuiPreferences,
)

_THEME_CHOICES = sorted(VALID_THEMES)
_STARTUP_CHOICES = sorted(VALID_STARTUP_VIEWS)
_LANG_CODES = list(LANGUAGES)
_LANG_LABELS = list(LANGUAGES.values())


class TuiSettingsPlugin(BasePlugin):
    LABEL = "Text UI settings"
    DESCRIPTION = (
        "Customise the TrueNAS TUI for your user account.\n\n"
        "  • Theme: default (blue), dark (green), high-contrast\n"
        "  • Startup view: system info pane or menu description\n"
        "  • Language\n\n"
        "Settings are saved to your account and persist across\n"
        "sessions on any client."
    )

    def run(self, stdscr, session) -> None:
        p = session.tui_prefs
        fields = [
            SectionField(key="", label=TRANSLATE("Appearance")),
            ChoiceField(
                key="theme",
                label=TRANSLATE("Theme"),
                choices=_THEME_CHOICES,
                value=_THEME_CHOICES.index(p.theme),
            ),
            SectionField(key="", label=TRANSLATE("Startup")),
            ChoiceField(
                key="startup_view",
                label=TRANSLATE("Startup view"),
                choices=_STARTUP_CHOICES,
                value=_STARTUP_CHOICES.index(p.startup_view),
            ),
            SectionField(key="", label=TRANSLATE("Locale")),
            ChoiceField(
                key="language",
                label=TRANSLATE("Language"),
                choices=_LANG_CODES,
                labels=_LANG_LABELS,
                value=_LANG_CODES.index(p.language),
            ),
        ]

        result = Form(stdscr, TRANSLATE("Text UI settings"), fields).run()
        if result is None:
            return

        new_prefs = TuiPreferences(**result)
        try:
            session.call("auth.set_attribute", TUI_PREFERENCES_KEY, asdict(new_prefs))
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        # Session prefs and side effects only after successful persist
        session.tui_prefs = new_prefs
        if new_prefs.language != p.language:
            setup_locale(new_prefs.language)
        if new_prefs.theme != p.theme:
            init_colors(new_prefs.theme)

        message_dialog(
            stdscr,
            TRANSLATE("Settings Saved"),
            TRANSLATE(
                "TUI preferences saved.\n"
                "Theme and locale changes take effect immediately."
            ),
        )
