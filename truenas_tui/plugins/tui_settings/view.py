from truenas_tui.api_methods import Method
from truenas_tui.localization import setup_locale
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.colors import reinit_colors
from truenas_tui.tui.dialogs import message_dialog
from truenas_tui.tui.forms import Form, BoolField, ChoiceField, SectionField
from truenas_tui.tui_preferences import (
    TUI_PREFERENCES_KEY, TuiPreferences, VALID_THEMES, VALID_STARTUP_VIEWS,
    DateFormat, TimeFormat, LANGUAGES,
)
from .localization import TRANSLATE

_THEME_CHOICES   = sorted(VALID_THEMES)
_STARTUP_CHOICES = sorted(VALID_STARTUP_VIEWS)

_DATE_FMT_CHOICES = [d.value for d in DateFormat]
_DATE_FMT_IDX     = {v: i for i, v in enumerate(_DATE_FMT_CHOICES)}

_TIME_FMT_CHOICES = [t.value for t in TimeFormat]
_TIME_FMT_LABELS  = [
    'HH:mm:ss (24-hour)',
    "hh:mm:ss a.m./p.m. (12-hour)",
    'hh:mm:ss AM/PM (12-hour)',
]
_TIME_FMT_IDX     = {v: i for i, v in enumerate(_TIME_FMT_CHOICES)}

_LANG_CODES  = list(LANGUAGES.keys())
_LANG_LABELS = list(LANGUAGES.values())
_LANG_IDX    = {code: i for i, code in enumerate(_LANG_CODES)}


class TuiSettingsPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset()   # every authenticated user
    LOCAL_ONLY           = False
    DEFAULT_HIDDEN       = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = ('Text UI settings')
    DESCRIPTION = (
        'Customise the TrueNAS TUI for your user account.\n\n'
        '  \u2022 Theme: default (blue), dark (green), high-contrast\n'
        '  \u2022 Startup view: system info pane or menu description\n'
        '  \u2022 Confirm dangerous actions (reboot, shutdown, reset)\n'
        '  \u2022 Language and date/time display formats\n\n'
        'Settings are saved to your account and persist across\n'
        'sessions on any client.'
    )

    def run(self, stdscr, session) -> None:
        p = session.tui_prefs
        theme_idx   = _THEME_CHOICES.index(p.theme)         if p.theme        in _THEME_CHOICES   else 0
        startup_idx = _STARTUP_CHOICES.index(p.startup_view) if p.startup_view in _STARTUP_CHOICES else 1
        lang_idx    = _LANG_IDX.get(p.language, _LANG_IDX.get('en', 0))
        date_idx    = _DATE_FMT_IDX.get(p.date_format, 0)
        time_idx    = _TIME_FMT_IDX.get(p.time_format, 0)

        fields = [
            SectionField('', TRANSLATE('Appearance')),
            ChoiceField('theme', TRANSLATE('Theme'), choices=_THEME_CHOICES, value=theme_idx),

            SectionField('', TRANSLATE('Startup')),
            ChoiceField('startup_view', TRANSLATE('Startup view'),
                        choices=_STARTUP_CHOICES, value=startup_idx),

            SectionField('', TRANSLATE('Behaviour')),
            BoolField('confirm_dangerous', TRANSLATE('Confirm dangerous actions'),
                      value=p.confirm_dangerous),

            SectionField('', TRANSLATE('Locale')),
            ChoiceField('language', TRANSLATE('Language'),
                        choices=_LANG_CODES, labels=_LANG_LABELS, value=lang_idx),
            ChoiceField('date_format', TRANSLATE('Date format'),
                        choices=_DATE_FMT_CHOICES, value=date_idx),
            ChoiceField('time_format', TRANSLATE('Time format'),
                        choices=_TIME_FMT_CHOICES, labels=_TIME_FMT_LABELS, value=time_idx),
        ]

        result = Form(stdscr, TRANSLATE('Text UI settings'), fields).run()
        if result is None:
            return

        # Snapshot for rollback on API failure
        snapshot = p.to_dict()

        p.theme             = result['theme']
        p.startup_view      = result['startup_view']
        p.confirm_dangerous = result['confirm_dangerous']
        p.language          = result['language']
        p.date_format       = result['date_format']
        p.time_format       = result['time_format']

        try:
            session.call(Method.AUTH_SET_ATTRIBUTE,
                         TUI_PREFERENCES_KEY, p.to_dict())
        except Exception as e:
            session.tui_prefs = TuiPreferences.from_dict(snapshot)
            message_dialog(stdscr, TRANSLATE('Error'), format_error(e))
            return

        # Side effects only after successful persist
        if result['language'] != snapshot['language']:
            setup_locale(result['language'])
        if result['theme'] != snapshot['theme']:
            reinit_colors(result['theme'])

        message_dialog(stdscr, TRANSLATE('Settings Saved'),
                       TRANSLATE('TUI preferences saved.\n'
                                 'Theme and locale changes take effect immediately.'))
