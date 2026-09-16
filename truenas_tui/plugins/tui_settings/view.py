from dataclasses import replace

from truenas_tui.api_methods import Method
from truenas_tui.localization import setup_locale
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.colors import reinit_colors
from truenas_tui.tui.dialogs import message_dialog
from truenas_tui.tui.forms import BoolField, ChoiceField, Form, SectionField
from truenas_tui.tui_preferences import (
    LANGUAGES,
    TUI_PREFERENCES_KEY,
    VALID_STARTUP_VIEWS,
    VALID_THEMES,
    DateFormat,
    TimeFormat,
)

from .localization import TRANSLATE

_THEME_CHOICES = sorted(VALID_THEMES)
_STARTUP_CHOICES = sorted(VALID_STARTUP_VIEWS)

_DATE_FMT_CHOICES = [d.value for d in DateFormat]
_DATE_FMT_IDX = {v: i for i, v in enumerate(_DATE_FMT_CHOICES)}

_TIME_FMT_CHOICES = [t.value for t in TimeFormat]
_TIME_FMT_LABELS = [
    "HH:mm:ss (24-hour)",
    "hh:mm:ss a.m./p.m. (12-hour)",
    "hh:mm:ss AM/PM (12-hour)",
]
_TIME_FMT_IDX = {v: i for i, v in enumerate(_TIME_FMT_CHOICES)}

_LANG_CODES = list(LANGUAGES.keys())
_LANG_LABELS = list(LANGUAGES.values())
_LANG_IDX = {code: i for i, code in enumerate(_LANG_CODES)}


class TuiSettingsPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset()  # every authenticated user
    LOCAL_ONLY = False
    DEFAULT_HIDDEN = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Text UI settings"
    DESCRIPTION = (
        "Customise the TrueNAS TUI for your user account.\n\n"
        "  \u2022 Theme: default (blue), dark (green), high-contrast\n"
        "  \u2022 Startup view: system info pane or menu description\n"
        "  \u2022 Confirm dangerous actions (reboot, shutdown, reset)\n"
        "  \u2022 Language and date/time display formats\n\n"
        "Settings are saved to your account and persist across\n"
        "sessions on any client."
    )

    def run(self, stdscr, session) -> None:
        p = session.tui_prefs
        theme_idx = _THEME_CHOICES.index(p.theme) if p.theme in _THEME_CHOICES else 0
        startup_idx = (
            _STARTUP_CHOICES.index(p.startup_view)
            if p.startup_view in _STARTUP_CHOICES
            else 1
        )
        lang_idx = _LANG_IDX.get(p.language, _LANG_IDX.get("en", 0))
        date_idx = _DATE_FMT_IDX.get(p.date_format, 0)
        time_idx = _TIME_FMT_IDX.get(p.time_format, 0)

        fields = [
            SectionField(key="", label=TRANSLATE("Appearance")),
            ChoiceField(
                key="theme",
                label=TRANSLATE("Theme"),
                choices=_THEME_CHOICES,
                value=theme_idx,
            ),
            SectionField(key="", label=TRANSLATE("Startup")),
            ChoiceField(
                key="startup_view",
                label=TRANSLATE("Startup view"),
                choices=_STARTUP_CHOICES,
                value=startup_idx,
            ),
            SectionField(key="", label=TRANSLATE("Behaviour")),
            BoolField(
                key="confirm_dangerous",
                label=TRANSLATE("Confirm dangerous actions"),
                value=p.confirm_dangerous,
            ),
            SectionField(key="", label=TRANSLATE("Locale")),
            ChoiceField(
                key="language",
                label=TRANSLATE("Language"),
                choices=_LANG_CODES,
                labels=_LANG_LABELS,
                value=lang_idx,
            ),
            ChoiceField(
                key="date_format",
                label=TRANSLATE("Date format"),
                choices=_DATE_FMT_CHOICES,
                value=date_idx,
            ),
            ChoiceField(
                key="time_format",
                label=TRANSLATE("Time format"),
                choices=_TIME_FMT_CHOICES,
                labels=_TIME_FMT_LABELS,
                value=time_idx,
            ),
        ]

        result = Form(stdscr, TRANSLATE("Text UI settings"), fields).run()
        if result is None:
            return

        new_prefs = replace(
            p,
            theme=result["theme"],
            startup_view=result["startup_view"],
            confirm_dangerous=result["confirm_dangerous"],
            language=result["language"],
            date_format=result["date_format"],
            time_format=result["time_format"],
        )

        try:
            session.call(
                Method.AUTH_SET_ATTRIBUTE, TUI_PREFERENCES_KEY, new_prefs.to_dict()
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        # Session prefs and side effects only after successful persist
        session.tui_prefs = new_prefs
        if new_prefs.language != p.language:
            setup_locale(new_prefs.language)
        if new_prefs.theme != p.theme:
            reinit_colors(new_prefs.theme)

        message_dialog(
            stdscr,
            TRANSLATE("Settings Saved"),
            TRANSLATE(
                "TUI preferences saved.\n"
                "Theme and locale changes take effect immediately."
            ),
        )
