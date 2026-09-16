import curses
import os
import pwd

from truenas_tui.plugins.base import BasePlugin

_SAFE_SHELLS = {
    "/usr/bin/sh",
    "/bin/sh",
    "/usr/bin/bash",
    "/bin/bash",
    "/usr/bin/dash",
    "/bin/dash",
    "/usr/bin/zsh",
    "/bin/zsh",
}


class LinuxShellPlugin(BasePlugin):
    LOCAL_ONLY = True
    LABEL = "Open Linux Shell"
    DESCRIPTION = (
        "Open a Linux shell (bash/zsh).\n"
        "\n"
        "Suspends the TUI and opens your login shell.\n"
        'Type "exit" or press Ctrl+D to return to the TUI.'
    )

    def run(self, stdscr, session) -> None:
        try:
            shell = pwd.getpwuid(os.getuid()).pw_shell
        except Exception:
            shell = ""
        if shell not in _SAFE_SHELLS:
            shell = "/usr/bin/zsh"
        curses.endwin()
        os.system(shell)
        stdscr.refresh()
