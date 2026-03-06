"""
Group 2 – Interface Mapping: CliShellPlugin and LinuxShellPlugin.

Both plugins are LOCAL_ONLY and require no API calls.  Tests verify:
  - Class attribute values (LOCAL_ONLY, REQUIRED_*_ROLES)
  - CliShell: shutil.which determines path; endwin+execv called or not
  - LinuxShell: pw_shell validated; safe → used directly, unsafe → fallback
               to /usr/bin/zsh; endwin → system → stdscr.refresh order

All real system calls (os.execv, os.system, curses.endwin, pwd.getpwuid,
shutil.which, os.getuid) are patched to avoid side effects.
"""
import pytest
from unittest.mock import patch, MagicMock, call

from truenas_tui.plugins.legacy_cli_shell.view import CliShellPlugin
from truenas_tui.plugins.legacy_linux_shell.view import LinuxShellPlugin, _SAFE_SHELLS


# ===========================================================================
# CliShellPlugin
# ===========================================================================

class TestCliShellPlugin:
    # -- class attributes ---------------------------------------------------

    def test_local_only_is_true(self):
        assert CliShellPlugin.LOCAL_ONLY is True

    def test_no_required_write_roles(self):
        assert CliShellPlugin.REQUIRED_WRITE_ROLES == set()

    def test_has_label(self):
        assert CliShellPlugin.LABEL  # non-empty string

    # -- midcli not found ---------------------------------------------------

    def test_not_found_shows_message_dialog(self, local_session, stdscr):
        with patch('shutil.which', return_value=None), \
             patch('truenas_tui.plugins.legacy_cli_shell.view.message_dialog') as mock_msg:
            CliShellPlugin().run(stdscr, local_session)

        mock_msg.assert_called_once()

    def test_not_found_no_execv(self, local_session, stdscr):
        with patch('shutil.which', return_value=None), \
             patch('truenas_tui.plugins.legacy_cli_shell.view.message_dialog'), \
             patch('os.execv') as mock_execv:
            CliShellPlugin().run(stdscr, local_session)

        mock_execv.assert_not_called()

    def test_not_found_no_endwin(self, local_session, stdscr):
        with patch('shutil.which', return_value=None), \
             patch('truenas_tui.plugins.legacy_cli_shell.view.message_dialog'), \
             patch('curses.endwin') as mock_endwin:
            CliShellPlugin().run(stdscr, local_session)

        mock_endwin.assert_not_called()

    # -- midcli found -------------------------------------------------------

    def test_found_calls_endwin(self, local_session, stdscr):
        with patch('shutil.which', return_value='/usr/bin/midcli'), \
             patch('curses.endwin') as mock_endwin, \
             patch('os.execv'):
            CliShellPlugin().run(stdscr, local_session)

        mock_endwin.assert_called_once()

    def test_found_calls_execv_with_path(self, local_session, stdscr):
        midcli = '/usr/bin/midcli'
        with patch('shutil.which', return_value=midcli), \
             patch('curses.endwin'), \
             patch('os.execv') as mock_execv:
            CliShellPlugin().run(stdscr, local_session)

        mock_execv.assert_called_once_with(midcli, [midcli])

    def test_endwin_called_before_execv(self, local_session, stdscr):
        order = []
        with patch('shutil.which', return_value='/usr/bin/midcli'), \
             patch('curses.endwin', side_effect=lambda: order.append('endwin')), \
             patch('os.execv', side_effect=lambda p, a: order.append('execv')):
            CliShellPlugin().run(stdscr, local_session)

        assert order == ['endwin', 'execv']

    def test_found_does_not_show_dialog(self, local_session, stdscr):
        with patch('shutil.which', return_value='/usr/bin/midcli'), \
             patch('curses.endwin'), \
             patch('os.execv'), \
             patch('truenas_tui.plugins.legacy_cli_shell.view.message_dialog') as mock_msg:
            CliShellPlugin().run(stdscr, local_session)

        mock_msg.assert_not_called()

    def test_which_called_with_midcli(self, local_session, stdscr):
        with patch('shutil.which', return_value=None) as mock_which, \
             patch('truenas_tui.plugins.legacy_cli_shell.view.message_dialog'):
            CliShellPlugin().run(stdscr, local_session)

        mock_which.assert_called_once_with('midcli')


# ===========================================================================
# LinuxShellPlugin
# ===========================================================================

class TestLinuxShellPlugin:
    # -- class attributes ---------------------------------------------------

    def test_local_only_is_true(self):
        assert LinuxShellPlugin.LOCAL_ONLY is True

    def test_no_required_write_roles(self):
        assert LinuxShellPlugin.REQUIRED_WRITE_ROLES == set()

    def test_has_label(self):
        assert LinuxShellPlugin.LABEL  # non-empty string

    # -- safe shells used directly ------------------------------------------

    @pytest.mark.parametrize('shell', sorted(_SAFE_SHELLS))
    def test_safe_shell_used_directly(self, shell, local_session, stdscr):
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid') as mock_pwd, \
             patch('curses.endwin'), \
             patch('os.system') as mock_sys:
            mock_pwd.return_value = MagicMock(pw_shell=shell)
            LinuxShellPlugin().run(stdscr, local_session)

        mock_sys.assert_called_once_with(shell)

    # -- unsafe shell falls back to /usr/bin/zsh ----------------------------

    @pytest.mark.parametrize('unsafe', [
        '/usr/bin/fish',
        '/usr/bin/tcsh',
        '/usr/bin/csh',
        '/usr/local/bin/fish',
        '/bin/login',
        '',
    ])
    def test_unsafe_shell_falls_back_to_zsh(self, unsafe, local_session, stdscr):
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid') as mock_pwd, \
             patch('curses.endwin'), \
             patch('os.system') as mock_sys:
            mock_pwd.return_value = MagicMock(pw_shell=unsafe)
            LinuxShellPlugin().run(stdscr, local_session)

        mock_sys.assert_called_once_with('/usr/bin/zsh')

    def test_getpwuid_exception_falls_back_to_zsh(self, local_session, stdscr):
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid', side_effect=KeyError('unknown uid')), \
             patch('curses.endwin'), \
             patch('os.system') as mock_sys:
            LinuxShellPlugin().run(stdscr, local_session)

        mock_sys.assert_called_once_with('/usr/bin/zsh')

    # -- call order ---------------------------------------------------------

    def test_endwin_called_before_system(self, local_session, stdscr):
        order = []
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid') as mock_pwd, \
             patch('curses.endwin', side_effect=lambda: order.append('endwin')), \
             patch('os.system', side_effect=lambda s: order.append('system')):
            mock_pwd.return_value = MagicMock(pw_shell='/usr/bin/zsh')
            LinuxShellPlugin().run(stdscr, local_session)

        assert order.index('endwin') < order.index('system')

    def test_stdscr_refresh_called_after_system(self, local_session, stdscr):
        refresh_order = []
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid') as mock_pwd, \
             patch('curses.endwin'), \
             patch('os.system', side_effect=lambda s: refresh_order.append('system')):
            mock_pwd.return_value = MagicMock(pw_shell='/usr/bin/zsh')
            stdscr.refresh.side_effect = lambda: refresh_order.append('refresh')
            LinuxShellPlugin().run(stdscr, local_session)

        assert 'refresh' in refresh_order
        assert refresh_order.index('system') < refresh_order.index('refresh')

    def test_stdscr_refresh_called_at_least_once(self, local_session, stdscr):
        with patch('os.getuid', return_value=0), \
             patch('pwd.getpwuid') as mock_pwd, \
             patch('curses.endwin'), \
             patch('os.system'):
            mock_pwd.return_value = MagicMock(pw_shell='/usr/bin/zsh')
            LinuxShellPlugin().run(stdscr, local_session)

        stdscr.refresh.assert_called()


# ===========================================================================
# _SAFE_SHELLS constant sanity checks
# ===========================================================================

def test_safe_shells_contains_bash():
    assert '/usr/bin/bash' in _SAFE_SHELLS


def test_safe_shells_contains_zsh():
    assert '/usr/bin/zsh' in _SAFE_SHELLS


def test_safe_shells_does_not_contain_fish():
    assert '/usr/bin/fish' not in _SAFE_SHELLS
