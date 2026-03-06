"""
Group 2 – Interface Mapping: Plugin visibility by mode and LOCAL_ONLY flag.

Tests can_activate() and LEGACY_ONLY across the full plugin registry, verifying:
  - Default mode: LEGACY_ONLY plugins hidden; all others visible
  - Legacy mode: sorted by LEGACY_INDEX; LOCAL_ONLY plugins hidden remotely
  - Plugin counts match expectations in each scenario
"""
import pytest

from truenas_tui.main import ALL_PLUGINS
from truenas_tui.plugins.legacy_cli_shell.view import CliShellPlugin
from truenas_tui.plugins.legacy_linux_shell.view import LinuxShellPlugin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(server):
    class Cfg:
        pass
    class Sess:
        config = Cfg()
    s = Sess()
    s.config.server = server
    return s


def _visible_default(roles: set, server) -> list:
    """Return plugin instances visible in default mode."""
    session = _make_session(server)
    ordered = [cls for cls in ALL_PLUGINS if not cls.LEGACY_ONLY and not cls.DEFAULT_HIDDEN]
    return [p for p in (cls() for cls in ordered)
            if p.can_activate(roles, session)]


def _visible_legacy(roles: set, server) -> list:
    """Return plugin instances visible in legacy mode, sorted by LEGACY_INDEX."""
    session = _make_session(server)
    ordered = sorted(
        [cls for cls in ALL_PLUGINS if cls.LEGACY_INDEX is not None],
        key=lambda cls: cls.LEGACY_INDEX,
    )
    return [p for p in (cls() for cls in ordered)
            if p.can_activate(roles, session)]


def _labels(plugins) -> list[str]:
    return [type(p).__name__ for p in plugins]


FULL_ADMIN_ROLES = {
    'FULL_ADMIN', 'NETWORK_INTERFACE_READ', 'NETWORK_INTERFACE_WRITE',
    'NETWORK_GENERAL_READ', 'NETWORK_GENERAL_WRITE',
    'ACCOUNT_READ', 'ACCOUNT_WRITE',
}


# ---------------------------------------------------------------------------
# LOCAL_ONLY behaviour
# ---------------------------------------------------------------------------

class TestLocalOnlyFiltering:
    def test_cli_shell_hidden_when_server_set(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        assert 'CliShellPlugin' not in names

    def test_linux_shell_hidden_when_server_set(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        assert 'LinuxShellPlugin' not in names

    def test_cli_shell_visible_when_server_none(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server=None)
        names = _labels(plugins)
        assert 'CliShellPlugin' in names

    def test_linux_shell_visible_when_server_none(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server=None)
        names = _labels(plugins)
        assert 'LinuxShellPlugin' in names

    def test_shell_plugins_in_legacy_index_order(self):
        """CliShell (7) must appear before LinuxShell (8) before RebootPlugin (9)."""
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server=None)
        names = _labels(plugins)
        assert 'ResetConfigPlugin' in names
        assert 'CliShellPlugin' in names
        assert 'LinuxShellPlugin' in names
        assert 'RebootPlugin' in names

        i_reset  = names.index('ResetConfigPlugin')
        i_cli    = names.index('CliShellPlugin')
        i_linux  = names.index('LinuxShellPlugin')
        i_reboot = names.index('RebootPlugin')

        assert i_reset < i_cli < i_linux < i_reboot

    def test_cli_shell_local_only_attr(self):
        assert CliShellPlugin.LOCAL_ONLY is True

    def test_linux_shell_local_only_attr(self):
        assert LinuxShellPlugin.LOCAL_ONLY is True


# ---------------------------------------------------------------------------
# LEGACY_ONLY behaviour
# ---------------------------------------------------------------------------

class TestLegacyOnlyFiltering:
    def test_legacy_only_plugins_absent_in_default_mode(self):
        """PasswordPlugin, ResetConfigPlugin, shells, Reboot, Shutdown hidden in default."""
        plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        for legacy_cls in ['PasswordPlugin', 'ResetConfigPlugin',
                           'CliShellPlugin', 'LinuxShellPlugin',
                           'RebootPlugin', 'ShutdownPlugin']:
            assert legacy_cls not in names, f'{legacy_cls} should not appear in default mode'

    def test_power_control_present_in_default_mode(self):
        plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        assert 'PowerControlPlugin' in names

    def test_power_control_absent_in_legacy_mode(self):
        """PowerControlPlugin has LEGACY_INDEX=None so it never appears in legacy mode."""
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        assert 'PowerControlPlugin' not in names

    def test_tui_settings_absent_in_legacy_mode(self):
        """TuiSettingsPlugin has LEGACY_INDEX=None so it never appears in legacy mode."""
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.1')
        names = _labels(plugins)
        assert 'TuiSettingsPlugin' not in names


# ---------------------------------------------------------------------------
# LEGACY_INDEX ordering
# ---------------------------------------------------------------------------

class TestLegacyIndexOrdering:
    def test_remote_legacy_order(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.108')
        names = _labels(plugins)
        expected = [
            'NetworkInterfacePlugin',   # 1
            'NetworkSettingsPlugin',    # 2
            'StaticRoutesPlugin',       # 3
            'PasswordPlugin',           # 4
            'OnetimePasswordPlugin',    # 5
            'ResetConfigPlugin',        # 6
            'RebootPlugin',             # 9
            'ShutdownPlugin',           # 10
        ]
        assert names == expected

    def test_local_legacy_order(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server=None)
        names = _labels(plugins)
        expected = [
            'NetworkInterfacePlugin',   # 1
            'NetworkSettingsPlugin',    # 2
            'StaticRoutesPlugin',       # 3
            'PasswordPlugin',           # 4
            'OnetimePasswordPlugin',    # 5
            'ResetConfigPlugin',        # 6
            'CliShellPlugin',           # 7
            'LinuxShellPlugin',         # 8
            'RebootPlugin',             # 9
            'ShutdownPlugin',           # 10
        ]
        assert names == expected

    def test_legacy_indices_are_monotonically_increasing(self):
        plugins = _visible_legacy(FULL_ADMIN_ROLES, server=None)
        indices = [p.LEGACY_INDEX for p in plugins if p.LEGACY_INDEX is not None]
        assert indices == sorted(indices)


# ---------------------------------------------------------------------------
# Total plugin counts
# ---------------------------------------------------------------------------

class TestPluginCounts:
    def test_default_remote_three_plugins(self):
        assert len(_visible_default(FULL_ADMIN_ROLES, server='192.168.1.108')) == 3

    def test_default_local_three_plugins(self):
        """No LOCAL_ONLY plugins in default mode, so count is same as remote."""
        assert len(_visible_default(FULL_ADMIN_ROLES, server=None)) == 3

    def test_legacy_remote_eight_plugins(self):
        assert len(_visible_legacy(FULL_ADMIN_ROLES, server='192.168.1.108')) == 8

    def test_legacy_local_ten_plugins(self):
        assert len(_visible_legacy(FULL_ADMIN_ROLES, server=None)) == 10

    def test_default_empty_roles_remote_count(self):
        # can_activate() only filters LOCAL_ONLY plugins (and PowerControl needs
        # FULL_ADMIN for writes, but can_activate() does not check roles).
        # All 3 default-mode plugins are visible regardless of roles.
        plugins = _visible_default(set(), server='192.168.1.108')
        assert len(plugins) == 3

    def test_legacy_empty_roles_remote_count(self):
        plugins = _visible_legacy(set(), server='192.168.1.108')
        assert len(plugins) == 8


# ---------------------------------------------------------------------------
# Default mode order
# ---------------------------------------------------------------------------

class TestDefaultModeOrder:
    def test_remote_default_order(self):
        plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.108')
        names = _labels(plugins)
        expected = ['NetworkPlugin', 'MyAccountPlugin', 'PowerControlPlugin']
        assert names == expected


# ---------------------------------------------------------------------------
# ALL_PLUGINS registry sanity
# ---------------------------------------------------------------------------

def test_all_plugins_is_ordered_list():
    assert isinstance(ALL_PLUGINS, list)
    assert len(ALL_PLUGINS) == 14


def test_all_plugin_classes_are_unique():
    assert len(ALL_PLUGINS) == len(set(ALL_PLUGINS))


def test_all_plugins_have_required_attributes():
    for cls in ALL_PLUGINS:
        instance = cls()
        assert hasattr(instance, 'LABEL')
        assert hasattr(instance, 'DESCRIPTION')
        assert hasattr(instance, 'REQUIRED_WRITE_ROLES')
        assert hasattr(instance, 'LOCAL_ONLY')
        assert hasattr(instance, 'LEGACY_INDEX')
        assert hasattr(instance, 'LEGACY_ONLY')
        assert hasattr(instance, 'DEFAULT_HIDDEN')
        assert hasattr(instance, 'REFRESH_INTERVAL')


def test_network_subplugins_hidden_in_default_mode():
    plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.108')
    names = _labels(plugins)
    for cls_name in ['NetworkInterfacePlugin', 'NetworkSettingsPlugin', 'StaticRoutesPlugin']:
        assert cls_name not in names


def test_tui_settings_hidden_in_default_mode():
    plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.108')
    assert 'TuiSettingsPlugin' not in _labels(plugins)


def test_network_plugin_present_in_default_mode():
    plugins = _visible_default(FULL_ADMIN_ROLES, server='192.168.1.108')
    assert 'NetworkPlugin' in _labels(plugins)
