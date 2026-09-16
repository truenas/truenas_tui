# truenas-tui

Terminal User Interface for TrueNAS, written in Python 3 using stdlib `curses`.

---

## Running

Requires Python 3.11 or newer and `truenas-api-client`, which is not on PyPI and is
installed from GitHub:

```bash
pip install "git+https://github.com/truenas/api_client.git"
```

Installing this package provides the `truenas-tui` command. From a checkout it can also
be started with `python -m truenas_tui.main`.

```
truenas-tui [--config FILE] [--menu]
```

`--config` selects a config file (default `~/.config/truenas_tui.conf`, see Configuration
below). `--menu` switches to the legacy numbered menu that mirrors `midcli --menu` and keeps
the expect scripts used by automated installs working.

On a TrueNAS system with no config file the TUI connects over the local middleware socket
and needs no credentials.

---

## Plugin system

### BasePlugin

All plugins subclass `truenas_tui.plugins.base.BasePlugin`.

**Class attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `REQUIRED_WRITE_ROLES` | `frozenset[str]` | Middleware RBAC roles required to make changes. Empty = write open to all authenticated users. |
| `LOCAL_ONLY` | `bool` | When `True`, hidden when the session uses a remote TCP connection. Default `False`. |
| `LABEL` | `str` | Menu label (English source string, translated on display). |
| `DESCRIPTION` | `str` | Multi-line description shown in the right pane when the item is selected. |

**Methods**

| Method | Description |
|--------|-------------|
| `can_write(roles)` | Returns `True` if the user's roles permit write operations in this plugin. |
| `get_label(session)` | Returns the translated menu label. Override for a dynamic label. |
| `get_description()` | Returns the translated description. |
| `run(stdscr, session)` | Takes over the screen. Must restore terminal state before returning. Abstract — subclasses must implement. |

### Plugin file layout

```
truenas_tui/plugins/<name>/
    __init__.py
    view.py          ← BasePlugin subclass
```

### Plugin registry

`DEFAULT_MENU` and `LEGACY_MENU` in `truenas_tui/main.py` list the plugins for each mode;
list order is menu order, and in `--menu` mode an item's number is its position in
`LEGACY_MENU`. `menu_plugins(session, menu_mode)` instantiates the right list and drops
`LOCAL_ONLY` plugins when the session is remote. `TuiSettingsPlugin` is in neither list and
is opened with the `s` hotkey.

`READONLY_ADMIN` minimum privilege is enforced globally at connect time.
`REQUIRED_WRITE_ROLES` reflects the actual middleware write role used by that plugin's API calls.

---

## UI layout

**Default mode** (3 items, remote or local):

```
┌─ TrueNAS 25.10.0 - hostname (server)  User: admin [FULL_ADMIN] ─┐
│ Menu                         │ Description / System Info         │
│  Network                     │                                   │
│  My Account                  │  <right pane>                     │
│  Power Control               │                                   │
├──────────────────────────────────────────────────────────────────┤
│ ↑↓/Enter Navigate/Select   r Refresh   s Settings   ^D/q Quit   │
└──────────────────────────────────────────────────────────────────┘
```

**Legacy mode** (`--menu`, 10 items local / 8 remote, numbered in order):

```
┌─ TrueNAS 25.10.0 - hostname (server)  User: admin [FULL_ADMIN] ─┐
│ Menu                         │ Description / System Info         │
│  1. Network interfaces       │                                   │
│  2. Network settings         │  <right pane>                     │
│  ...                         │                                   │
│ 10. Reboot                   │                                   │
├──────────────────────────────────────────────────────────────────┤
│ Enter an option from 1-10: ↑↓/Enter Navigate/Select  ^D/q Quit  │
└──────────────────────────────────────────────────────────────────┘
```

**Right-pane modes**

- **Info mode** (default on startup, or Esc from menu): shows `system.info` table, auto-refreshes every 10 seconds.
- **Description mode**: triggered by any navigation key; shows the selected plugin's `DESCRIPTION`.

**Keyboard shortcuts**

| Key | Action |
|-----|--------|
| `1`–`9` | Directly select and activate that menu item (`--menu` mode only, expect-script compatible) |
| `↑` / `↓` | Move selection |
| `Enter` | Activate selected item |
| `r` | Force-refresh system info |
| `s` | Open TUI Settings (default mode only) |
| `Esc` | Return to system info view |
| `q` / `Ctrl+D` | Quit |

In `--menu` mode the footer shows `Enter an option from 1-N:` so the expect scripts used by
automated installs keep working. Default mode has no numbered prompt.

---

## Localization

`truenas_tui/localization.py` exposes two functions. `setup_locale(language)` loads
`truenas_tui/i18n/<language>.json`, a flat `{"English string": "Translation"}` dict, and
`TRANSLATE(text)` looks a string up in it, returning the English source text when there is no
entry. English and unknown language codes load no table, so everything passes through unchanged.

Every module imports `TRANSLATE` from that one place; plugin `LABEL` and `DESCRIPTION` class
attributes hold the English source string and are translated on display.

Language is taken from `tui_preferences.language` (stored under `auth.me → attributes.tui_preferences`),
seeded on first run from `auth.me → attributes.preferences.language`.

77 languages ship as package data under `truenas_tui/i18n/`. `i18n/update_translations.py`
removes entries no longer used in the source and machine-translates missing ones (it needs
`pip install deep-translator`). A test fails when the language files are out of step with the
source strings.

---

## TUI preferences

Press `s` in default mode to open the settings form. Preferences are stored on the user
account under `auth.me → attributes.tui_preferences` (written with `auth.set_attribute`), so
they follow the user to any client. On first run they are seeded from the Web UI preferences
(language).

| Key | Values | Default |
|-----|--------|---------|
| `language` | any code in `LANGUAGES` (`truenas_tui/tui_preferences.py`) | `en` |
| `theme` | `default`, `dark`, `high_contrast` | `default` |
| `startup_view` | `sysinfo`, `menu` | `sysinfo` |

Unknown keys are ignored and invalid values fall back to the defaults when loaded.

---

## Adding a new plugin

1. Create `truenas_tui/plugins/<name>/` with `__init__.py` and `view.py`.

2. **`view.py`**: subclass `BasePlugin`; set `REQUIRED_WRITE_ROLES`, `LABEL`, `DESCRIPTION`;
   implement `run(stdscr, session)`. Import `TRANSLATE` from `truenas_tui.localization` for
   any other user-facing string.

   Forms are built from the field classes in `truenas_tui/tui/forms.py` (`FormField`,
   `BoolField`, `ChoiceField`, `IntField`, `ListField`, `SectionField`). They are frozen,
   keyword-only dataclasses, so construct them with named arguments:
   ```python
   fields = [
       SectionField(key="", label=TRANSLATE("Network")),
       FormField(key="hostname", label=TRANSLATE("Hostname"), value=current),
       BoolField(key="dhcp", label=TRANSLATE("Use DHCP"), value=True),
   ]
   # Returns a dict of typed values, or None if cancelled
   result = Form(stdscr, TRANSLATE("Title"), fields).run()
   ```

3. Call the middleware with plain method strings: `session.call("system.info")`.

4. Add the class to `DEFAULT_MENU` or `LEGACY_MENU` in `truenas_tui/main.py` (position = menu order).

5. Add mock responses to the dispatch table in `tests/mock_session.py`, keyed by method string.

6. Run `python3 i18n/update_translations.py` to add the new strings to every language file.

---

## Configuration

Default config path: `~/.config/truenas_tui.conf`

```ini
[truenas]
server       = truenas.example.com
username     = admin
api_key_path = /path/to/api.key
verify_ssl   = true            ; set false only for self-signed certificates
```

Omit `server` (or leave the file absent) to connect over the local middleware socket
(`/var/run/middleware/middlewared.sock` on a TrueNAS system, no authentication required on-box).

---

## Running tests

```bash
# Test dependencies (the API client is not on PyPI)
pip install "git+https://github.com/truenas/api_client.git" pytest pexpect

# Full unit/integration test suite (no network required)
python -m pytest tests/ -v

# Mock TUI (interactive, no network required)
python tests/run_mock_tui.py

# Live read-only tests (requires a configured TrueNAS server)
python3 tests/test_live_readonly.py --config /path/to/config.conf
```
