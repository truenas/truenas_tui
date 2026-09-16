import curses
import os
import shutil

from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui.dialogs import message_dialog

from .localization import TRANSLATE


class CliShellPlugin(BasePlugin):
    LOCAL_ONLY = True
    LEGACY_INDEX = 7
    LEGACY_ONLY = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Open TrueNAS CLI Shell"
    DESCRIPTION = (
        "Open the TrueNAS interactive CLI shell (midcli).\n"
        "\n"
        "Replaces the TUI with the full midcli command-line\n"
        "interface. The TUI restarts after you exit midcli."
    )

    def run(self, stdscr, session) -> None:
        midcli_path = shutil.which("midcli")
        if not midcli_path:
            message_dialog(
                stdscr,
                TRANSLATE("Not Found"),
                TRANSLATE("midcli is not available on this system."),
            )
            return
        curses.endwin()
        os.execv(midcli_path, [midcli_path])
        # execv does not return; if it fails an OSError is raised and
        # caught by _activate_selected → shown as error dialog
