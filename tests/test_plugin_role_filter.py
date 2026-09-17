"""
Plugin visibility by mode and LOCAL_ONLY flag.

Tests menu_plugins() over DEFAULT_MENU and LEGACY_MENU, verifying:
  - Default mode: the three top-level plugins, regardless of connection type
  - Legacy mode: midcli order; LOCAL_ONLY plugins hidden on remote sessions
"""

from truenas_tui.main import DEFAULT_MENU, LEGACY_MENU, menu_plugins
from truenas_tui.plugins.legacy_cli_shell.view import CliShellPlugin
from truenas_tui.plugins.legacy_linux_shell.view import LinuxShellPlugin


def _session(server):
    class Cfg:
        pass

    class Sess:
        config = Cfg()

    s = Sess()
    s.config.server = server
    return s


def _names(server, menu_mode: bool) -> list[str]:
    names = []
    for p in menu_plugins(_session(server), menu_mode):
        names.append(type(p).__name__)
    return names


class TestLocalOnlyFiltering:
    def test_shells_hidden_when_server_set(self):
        names = _names("192.168.1.1", menu_mode=True)
        assert "CliShellPlugin" not in names
        assert "LinuxShellPlugin" not in names

    def test_shells_visible_when_server_none(self):
        names = _names(None, menu_mode=True)
        assert "CliShellPlugin" in names
        assert "LinuxShellPlugin" in names

    def test_shell_plugins_are_local_only(self):
        assert CliShellPlugin.LOCAL_ONLY is True
        assert LinuxShellPlugin.LOCAL_ONLY is True


class TestLegacyOrder:
    def test_remote_legacy_order(self):
        assert _names("192.168.1.108", menu_mode=True) == [
            "NetworkInterfacePlugin",
            "NetworkSettingsPlugin",
            "StaticRoutesPlugin",
            "PasswordPlugin",
            "OnetimePasswordPlugin",
            "ResetConfigPlugin",
            "RebootPlugin",
            "ShutdownPlugin",
        ]

    def test_local_legacy_order(self):
        assert _names(None, menu_mode=True) == [
            "NetworkInterfacePlugin",
            "NetworkSettingsPlugin",
            "StaticRoutesPlugin",
            "PasswordPlugin",
            "OnetimePasswordPlugin",
            "ResetConfigPlugin",
            "CliShellPlugin",
            "LinuxShellPlugin",
            "RebootPlugin",
            "ShutdownPlugin",
        ]

    def test_legacy_menu_has_ten_items(self):
        assert len(LEGACY_MENU) == 10

    def test_power_and_settings_plugins_not_in_legacy_menu(self):
        names = _names(None, menu_mode=True)
        assert "PowerControlPlugin" not in names
        assert "TuiSettingsPlugin" not in names


class TestDefaultMode:
    def test_default_order(self):
        assert _names("192.168.1.108", menu_mode=False) == [
            "NetworkPlugin",
            "MyAccountPlugin",
            "PowerControlPlugin",
        ]

    def test_default_local_same_as_remote(self):
        assert _names(None, menu_mode=False) == _names("192.168.1.108", False)

    def test_legacy_plugins_absent_in_default_mode(self):
        names = _names("192.168.1.108", menu_mode=False)
        for cls in LEGACY_MENU:
            assert cls.__name__ not in names

    def test_settings_plugin_absent_in_default_mode(self):
        assert "TuiSettingsPlugin" not in _names("192.168.1.108", menu_mode=False)


def test_menus_do_not_overlap():
    assert not set(DEFAULT_MENU) & set(LEGACY_MENU)
    assert len(LEGACY_MENU) == len(set(LEGACY_MENU))


def test_all_plugins_have_required_attributes():
    for cls in DEFAULT_MENU + LEGACY_MENU:
        instance = cls()
        assert hasattr(instance, "LABEL")
        assert hasattr(instance, "DESCRIPTION")
        assert hasattr(instance, "REQUIRED_WRITE_ROLES")
        assert hasattr(instance, "LOCAL_ONLY")
