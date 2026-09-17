"""Unit tests for truenas_tui/tui/colors.py."""

import curses
from unittest.mock import patch

from truenas_tui.tui import colors


def test_pair_plain_in_default_theme(monkeypatch):
    monkeypatch.setattr(colors, "_active_theme", "default")
    with patch("curses.color_pair", return_value=0):
        assert colors.pair(colors.HEADER) == 0


def test_pair_adds_reverse_in_high_contrast(monkeypatch):
    monkeypatch.setattr(colors, "_active_theme", "high_contrast")
    with patch("curses.color_pair", return_value=0):
        assert colors.pair(colors.HEADER) & curses.A_REVERSE
        assert colors.pair(colors.MENU_SELECTED) & curses.A_REVERSE
        assert colors.pair(colors.ERROR) & curses.A_REVERSE
        assert not colors.pair(colors.DIM) & curses.A_REVERSE
