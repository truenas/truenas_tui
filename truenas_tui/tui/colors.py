"""Curses color pair definitions and multi-theme support."""

import curses

HEADER = 1
MENU_NORMAL = 2
MENU_SELECTED = 3
BORDER = 4
WARNING = 5
ERROR = 6
SUCCESS = 7
DIM = 8
TITLE = 9

_active_theme: str = "default"

# Pairs that get A_REVERSE injected in high_contrast mode
_HIGH_CONTRAST_REVERSE = frozenset({HEADER, MENU_SELECTED, ERROR})


def init_colors(theme: str = "default") -> None:
    """Initialise curses color pairs. Safe to call multiple times (live reload)."""
    global _active_theme
    valid = {"default", "dark", "high_contrast"}
    _active_theme = theme if theme in valid else "default"

    curses.start_color()
    curses.use_default_colors()

    W = curses.COLOR_WHITE
    BL = curses.COLOR_BLUE
    CY = curses.COLOR_CYAN
    BK = curses.COLOR_BLACK
    R = curses.COLOR_RED
    G = curses.COLOR_GREEN
    Y = curses.COLOR_YELLOW

    palettes = {
        "default": [
            (HEADER, W, BL),
            (MENU_NORMAL, -1, -1),
            (MENU_SELECTED, BK, CY),
            (BORDER, BL, -1),
            (WARNING, R, -1),
            (ERROR, W, R),
            (SUCCESS, G, -1),
            (DIM, BK, -1),
            (TITLE, W, -1),
        ],
        "dark": [
            (HEADER, G, BK),
            (MENU_NORMAL, -1, -1),
            (MENU_SELECTED, BK, G),
            (BORDER, G, -1),
            (WARNING, Y, -1),
            (ERROR, W, R),
            (SUCCESS, G, -1),
            (DIM, BK, -1),
            (TITLE, G, -1),
        ],
        "high_contrast": [
            # All pairs use terminal defaults; pair() injects A_REVERSE
            # for HEADER, MENU_SELECTED, ERROR via _HIGH_CONTRAST_REVERSE.
            (HEADER, -1, -1),
            (MENU_NORMAL, -1, -1),
            (MENU_SELECTED, -1, -1),
            (BORDER, -1, -1),
            (WARNING, -1, -1),
            (ERROR, -1, -1),
            (SUCCESS, -1, -1),
            (DIM, -1, -1),
            (TITLE, -1, -1),
        ],
    }
    for pair_id, fg, bg in palettes[_active_theme]:
        curses.init_pair(pair_id, fg, bg)


def reinit_colors(theme: str) -> None:
    """Re-apply a different theme mid-session."""
    init_colors(theme)


def pair(color_id: int) -> int:
    """Return the curses attribute for color_id, including theme-specific adjustments."""
    attr = curses.color_pair(color_id)
    if _active_theme == "high_contrast" and color_id in _HIGH_CONTRAST_REVERSE:
        attr |= curses.A_REVERSE
    return attr
