# truenas-tui

Terminal User Interface for TrueNAS, written in Python 3 using stdlib `curses`.

---

## Plugin system

### BasePlugin

All plugins subclass `truenas_tui.plugins.base.BasePlugin`.

**Class attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `REQUIRED_WRITE_ROLES` | `frozenset[str]` | Middleware RBAC roles required to make changes. Empty = write open to all authenticated users. |
| `LOCAL_ONLY` | `bool` | When `True`, hidden when the session uses a remote TCP connection. Default `False`. |
| `LEGACY_INDEX` | `int \| None` | Position in `--menu` (legacy) mode. `None` = not in legacy menu. |
| `LEGACY_ONLY` | `bool` | When `True`, hidden in default (non-legacy) mode. |
| `DEFAULT_HIDDEN` | `bool` | When `True`, hidden from the default-mode main menu (e.g. accessible via hotkey only). |
| `LABEL` | `str` | Default menu label string. |
| `DESCRIPTION` | `str` | Multi-line description shown in the right pane when the item is selected. |
| `REFRESH_INTERVAL` | `int` | Seconds between automatic label refreshes from the main-view tick loop. `0` (default) = never auto-refresh. |

**Methods**

| Method | Description |
|--------|-------------|
| `can_activate(roles, session=None)` | Returns `True` if the user's roles permit showing this plugin. Also hides `LOCAL_ONLY` plugins when `session.config.server` is set. Evaluated at startup; failing plugins are excluded from the menu. |
| `can_write(roles)` | Returns `True` if the user's roles permit write operations in this plugin. |
| `get_label(session)` | Returns the menu label, calling `_fetch_label()` on first call and caching the result. |
| `_fetch_label(session)` | Override to compute a dynamic label (called once, then cached). Default returns `LABEL`. |
| `refresh(session)` | Busts the label cache and records the refresh timestamp. |
| `needs_refresh()` | Returns `True` when `REFRESH_INTERVAL` seconds have elapsed since the last `refresh()` call. |
| `run(stdscr, session)` | Takes over the screen. Must restore terminal state before returning. Abstract — subclasses must implement. |

### Plugin file layout

```
truenas_tui/plugins/<name>/
    __init__.py
    view.py          ← BasePlugin subclass
    localization.py  ← make_translator('<name>') → (_, ngettext)
```

### Plugin registry

`ALL_PLUGINS` in `truenas_tui/main.py` — list order determines menu order.

`READONLY_ADMIN` minimum privilege is enforced globally at connect time.
`REQUIRED_WRITE_ROLES` reflects the actual middleware write role used by that plugin's API calls.

### Label caching

`get_label()` calls `_fetch_label()` once and caches the result in `_label_cache`.
`refresh()` deletes `_label_cache` and stamps `_last_refresh`.
`needs_refresh()` returns `True` when `REFRESH_INTERVAL` seconds have elapsed since `_last_refresh`.

The main view's 1-second tick loop calls `plugin.needs_refresh()` on the currently selected plugin and, when true, calls `plugin.refresh(session)` to trigger a label re-fetch on the next draw.

---

## UI layout

**Default mode** (3 items, remote or local):

```
┌─ TrueNAS 25.10.0 - hostname (server)  User: admin [FULL_ADMIN] ─┐
│ Menu                         │ Description / System Info         │
│  1. Network                  │                                   │
│  2. My Account               │  <right pane>                     │
│  3. Power Control            │                                   │
├──────────────────────────────────────────────────────────────────┤
│ Enter an option from 1-3:  ↑↓/Enter Navigate/Select  ^D/q Quit  │
└──────────────────────────────────────────────────────────────────┘
```

**Legacy mode** (`--menu`, up to 10 items local / 8 remote):

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
| `1`–`9` | Directly select and activate that menu item (expect-script compatible) |
| `↑` / `↓` | Move selection |
| `Enter` | Activate selected item |
| `r` | Force-refresh all plugin labels and system info |
| `s` | Open TUI Settings (default mode only) |
| `Esc` | Return to system info view |
| `q` / `Ctrl+D` | Quit |

The footer always shows `Enter an option from 1-N:` for pexpect expect-script compatibility.

---

## Localization

### Overview

Central gettext setup lives in `truenas_tui/localization.py`.
`make_translator(domain)` returns `(_, ngettext)` bound to a named gettext domain.

Language is taken from `tui_preferences.language` (stored under `auth.me → attributes.tui_preferences`),
seeded on first run from `auth.me → attributes.preferences.language`.
`setup_locale(language)` validates the BCP-47 tag and clears the translation cache.

### Per-plugin domains

Each plugin's `localization.py` calls `make_translator('<plugin_name>')` to get its own `_` function.
All plugins share the same source-tree locale directory but have separate `.po` files.

### Locale file paths

```
truenas_tui/locale/
    DOMAINS                          ← one domain name per line
    <lang>/LC_MESSAGES/<domain>.po   ← source translation file
    <lang>/LC_MESSAGES/<domain>.mo   ← compiled binary (not committed)
```

`.mo` files are produced by `msgfmt` during the Debian package build (see `debian/rules`).

On an installed system, gettext searches `sys.prefix/share/locale` (i.e. `/usr/share/locale`).
`fallback=True` means untranslated strings pass through as-is.

87 languages are supported. Translation source files live in `i18n/<lang>.json` (flat
`{"English string": "Translation"}` dicts). `i18n/gen_locale.py` converts them to
`.po`/`.mo` files at build time.

### Domains

Listed in `truenas_tui/locale/DOMAINS`:

```
truenas_tui          ← core / shared strings
network_interface
network_settings
static_routes
my_account
network
legacy_password
onetime_password
legacy_reset_config
legacy_cli_shell
legacy_linux_shell
legacy_reboot
legacy_shutdown
tui_settings
power_control
```

---

## API methods

All API method strings are defined in `truenas_tui/api_methods.py` as `class Method(StrEnum)`.

`session.call(Method.SOME_METHOD, ...)` — `StrEnum` members compare and behave as plain strings,
so they are fully compatible with the underlying `truenas_api_client.Client.call()` signature.

---

## Adding a new plugin

1. Create `truenas_tui/plugins/<name>/` with `__init__.py`, `view.py`, `localization.py`.

2. **`localization.py`**:
   ```python
   from truenas_tui.localization import make_translator

   _, ngettext = make_translator("<name>")
   ```

3. **`view.py`**: subclass `BasePlugin`; set `REQUIRED_WRITE_ROLES`, `LABEL`, `DESCRIPTION`;
   implement `run(stdscr, session)`.

4. Add any new API methods to `truenas_tui/api_methods.py` as `Method` enum members.

5. Register the class in `ALL_PLUGINS` in `truenas_tui/main.py` (position = menu order).

6. Add mock responses to `tests/mock_session.py` dispatch table using `Method.<CONSTANT>` keys.

7. **Localization**: new `_('...')` strings are automatically part of the `<name>` domain.
   To expose them for translation:
   - Add `<name>` to `truenas_tui/locale/DOMAINS`
   - Add the English strings to each `i18n/<lang>.json` (or run `python3 i18n/gen_locale.py --update-json` to machine-translate missing entries)
   - Run `python3 i18n/gen_locale.py` to regenerate all `.po`/`.mo` files

---

## Configuration

Default config path: `~/.config/truenas_tui.conf`

```ini
[truenas]
server       = truenas.example.com
username     = admin
api_key_path = /path/to/api.key
```

Omit `server` (or leave the file absent) to attempt a local AF_UNIX connection to
`/var/run/middlewared.sock` (no authentication required on-box).

---

## Running tests

```bash
# Full unit/integration test suite (no network required)
python -m pytest tests/ -v

# Mock TUI (interactive, no network required)
python tests/run_mock_tui.py

# Live read-only tests (requires a configured TrueNAS server)
python -m pytest tests/test_live_readonly.py -v
```
