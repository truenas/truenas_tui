"""
Unit tests for truenas_tui/tui/dialogs.py.

All tests patch curses.newwin, curses.curs_set, and curses.color_pair to avoid
requiring a real terminal.  The mock_win fixture controls input via getch.side_effect.
"""

import curses
from unittest.mock import MagicMock, patch

import pytest

from truenas_tui.tui import HardExit, colors
from truenas_tui.tui.dialogs import (
    _center_win,
    _draw_box,
    _restore_screen,
    _save_screen,
    confirm_dialog,
    input_dialog,
    message_dialog,
    select_dialog,
)


def _dialog_patches(mock_win):
    """Return a list of patch context managers used across all dialog tests."""
    return [
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ]


def test_draw_box_calls_box(mock_win):
    _draw_box(mock_win)
    mock_win.box.assert_called_once()


def test_draw_box_with_title(mock_win):
    mock_win.getmaxyx.return_value = (5, 40)
    with patch("curses.color_pair", return_value=0):
        _draw_box(mock_win, title="My Title")
    mock_win.box.assert_called_once()
    # addstr should have been called for the title
    mock_win.addstr.assert_called()


def test_center_win_position(stdscr, mock_win):
    stdscr.getmaxyx.return_value = (24, 80)
    with patch("curses.newwin", return_value=mock_win) as mock_newwin:
        win = _center_win(stdscr, 10, 50)
    # Should compute centered position: y=(24-10)//2=7, x=(80-50)//2=15
    mock_newwin.assert_called_once_with(10, 50, 7, 15)
    assert win is mock_win


def test_save_screen_dupwin_available(stdscr):
    fake_saved = MagicMock()
    stdscr.dupwin = MagicMock(return_value=fake_saved)
    result = _save_screen(stdscr)
    assert result is fake_saved


def test_save_screen_no_dupwin(stdscr):
    del stdscr.dupwin  # MagicMock will raise AttributeError

    def _raise_attribute_error(self):
        raise AttributeError

    stdscr.dupwin = property(_raise_attribute_error)

    # Use a regular object without dupwin
    class NoDupwin:
        @property
        def dupwin(self):
            raise AttributeError("no dupwin")

    result = _save_screen(NoDupwin())
    assert result is None


def test_restore_screen_with_saved(stdscr):
    saved = MagicMock()
    _restore_screen(stdscr, saved)
    stdscr.overlay.assert_called_once_with(saved)
    stdscr.refresh.assert_called_once()


def test_restore_screen_no_saved(stdscr):
    _restore_screen(stdscr, None)
    stdscr.touchwin.assert_called_once()
    stdscr.refresh.assert_called_once()


def test_message_dialog_enter_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Title", "Hello world")  # should not raise


def test_message_dialog_space_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord(" ")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Info", "Press space")


def test_message_dialog_q_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("q")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Info", "Press q")


def test_message_dialog_esc_key(stdscr, mock_win):
    mock_win.getch.side_effect = [27]  # Esc
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Info", "Press esc")


def test_message_dialog_ctrl_d(stdscr, mock_win):
    mock_win.getch.side_effect = [4]  # Ctrl+D
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            message_dialog(stdscr, "Title", "Message")


def test_message_dialog_multiline(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Title", "Line 1\nLine 2\nLine 3")


def test_message_dialog_timeout_auto_dismiss(stdscr, mock_win):
    # -1 = timeout ticks (decrement), then ord('\n') to dismiss early
    mock_win.getch.side_effect = [-1, -1, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "OTP", "secret123", timeout_secs=5)
    # After 2 ticks (remaining becomes 3), user pressed Enter
    mock_win.timeout.assert_called()


def test_message_dialog_timeout_ctrl_d(stdscr, mock_win):
    """Ctrl+D inside the timeout countdown loop raises HardExit."""
    mock_win.getch.side_effect = [4]  # Ctrl+D on first tick
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            message_dialog(stdscr, "Title", "Message", timeout_secs=5)


def test_message_dialog_timeout_key_dismiss(stdscr, mock_win):
    """Any dismiss key inside the timeout loop breaks out."""
    mock_win.getch.side_effect = [ord("q")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Title", "Message", timeout_secs=5)


def test_confirm_dialog_yes_default_enter(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Are you sure?")
    assert result is True


def test_confirm_dialog_tab_then_enter(stdscr, mock_win):
    """Tab switches to No, Enter confirms No."""
    mock_win.getch.side_effect = [ord("\t"), ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Are you sure?")
    assert result is False


def test_confirm_dialog_y_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("y")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Delete?")
    assert result is True


def test_confirm_dialog_n_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Delete?")
    assert result is False


def test_confirm_dialog_esc(stdscr, mock_win):
    mock_win.getch.side_effect = [27]  # Esc → No
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Continue?")
    assert result is False


def test_confirm_dialog_left_right_toggle(stdscr, mock_win):
    """Left/Right toggles, two toggles returns to Yes."""
    mock_win.getch.side_effect = [curses.KEY_LEFT, curses.KEY_RIGHT, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Toggle back?")
    assert result is True


def test_confirm_dialog_ctrl_d(stdscr, mock_win):
    mock_win.getch.side_effect = [4]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            confirm_dialog(stdscr, "Confirm", "Exit?")


def test_confirm_dialog_N_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("N")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Sure?")
    assert result is False


def test_confirm_dialog_Y_key(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("Y")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = confirm_dialog(stdscr, "Confirm", "Sure?")
    assert result is True


def test_input_dialog_simple_entry(stdscr, mock_win):
    # Type 'hello' then Enter
    keys = [ord("h"), ord("e"), ord("l"), ord("l"), ord("o"), ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter text:")
    assert result == "hello"


def test_input_dialog_esc(stdscr, mock_win):
    mock_win.getch.side_effect = [27]  # Esc → cancel
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter text:")
    assert result is None


def test_input_dialog_ctrl_d(stdscr, mock_win):
    mock_win.getch.side_effect = [4]  # Ctrl+D
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            input_dialog(stdscr, "Title", "Enter text:")


def test_input_dialog_backspace(stdscr, mock_win):
    # Type 'hi', backspace, type 'x', Enter
    keys = [ord("h"), ord("i"), curses.KEY_BACKSPACE, ord("x"), ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:")
    assert result == "hx"


def test_input_dialog_ctrl_u_clears(stdscr, mock_win):
    keys = [ord("a"), ord("b"), ord("c"), 21, ord("\n")]  # Ctrl+U = 21
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:")
    assert result == ""


def test_input_dialog_home_end(stdscr, mock_win):
    # Type 'b', go home (Ctrl+A), type 'a', end (Ctrl+E), Enter
    # Result should be 'ab' since we insert 'a' at position 0
    keys = [ord("b"), 1, ord("a"), ord("\n")]  # Ctrl+A = 1
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:")
    assert result == "ab"


def test_input_dialog_default_value(stdscr, mock_win):
    # Press Enter immediately to accept default
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:", default="prefilled")
    assert result == "prefilled"


def test_input_dialog_secret_mode_rejects_high_byte(stdscr, mock_win):
    # High byte (> 0x7e) should be rejected in secret mode
    # Latin-1 char 0xe9 = 233, accepted in non-secret but rejected in secret
    keys = [0xE9, ord("\n")]  # high byte then Enter
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Password:", secret=True)
    assert result == ""  # high byte was rejected


def test_input_dialog_secret_mode_accepts_ascii(stdscr, mock_win):
    keys = [ord("p"), ord("a"), ord("s"), ord("s"), ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Password:", secret=True)
    assert result == "pass"


def test_input_dialog_non_secret_accepts_extended(stdscr, mock_win):
    # Non-secret mode: 0xe9 (é) should be accepted
    keys = [0xE9, ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:", secret=False)
    assert result == chr(0xE9)


def test_input_dialog_left_right_cursor(stdscr, mock_win):
    # Type 'ab', go left, type 'x', Enter → 'axb'
    keys = [ord("a"), ord("b"), curses.KEY_LEFT, ord("x"), ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:")
    assert result == "axb"


def test_input_dialog_delete_key(stdscr, mock_win):
    # Type 'ab', go left, delete (KEY_DC), Enter → 'a'
    keys = [ord("a"), ord("b"), curses.KEY_LEFT, curses.KEY_DC, ord("\n")]
    mock_win.getch.side_effect = keys
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = input_dialog(stdscr, "Title", "Enter:")
    assert result == "a"


def test_select_dialog_empty_options(stdscr, mock_win):
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", [])
    assert result is None


def test_select_dialog_enter_selects_current(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta", "Gamma"])
    assert result == 0  # default selected=0


def test_select_dialog_down_then_enter(stdscr, mock_win):
    mock_win.getch.side_effect = [curses.KEY_DOWN, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta", "Gamma"])
    assert result == 1


def test_select_dialog_up_then_enter(stdscr, mock_win):
    # Start at index 1, go up, Enter
    mock_win.getch.side_effect = [curses.KEY_UP, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta", "Gamma"], selected=1)
    assert result == 0


def test_select_dialog_q_cancel(stdscr, mock_win):
    mock_win.getch.side_effect = [ord("q")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta"])
    assert result is None


def test_select_dialog_esc_cancel(stdscr, mock_win):
    mock_win.getch.side_effect = [27]  # Esc
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta"])
    assert result is None


def test_select_dialog_number_key(stdscr, mock_win):
    # Press '2' → returns index 1 (1-based → 0-based)
    mock_win.getch.side_effect = [ord("2")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta", "Gamma"])
    assert result == 1


def test_select_dialog_ctrl_d(stdscr, mock_win):
    mock_win.getch.side_effect = [4]  # Ctrl+D
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        with pytest.raises(HardExit):
            select_dialog(stdscr, "Pick", ["Alpha", "Beta"])


def test_select_dialog_number_out_of_range(stdscr, mock_win):
    # '9' when only 2 options → no action, next key Enter at current=0
    mock_win.getch.side_effect = [ord("9"), ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta"])
    assert result == 0  # stayed at 0


def test_select_dialog_up_at_top_stays(stdscr, mock_win):
    # At top, up arrow stays at 0
    mock_win.getch.side_effect = [curses.KEY_UP, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta", "Gamma"], selected=0)
    assert result == 0


def test_select_dialog_down_at_bottom_stays(stdscr, mock_win):
    # At bottom, down arrow stays
    mock_win.getch.side_effect = [curses.KEY_DOWN, ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        result = select_dialog(stdscr, "Pick", ["Alpha", "Beta"], selected=1)
    assert result == 1  # stayed at 1


def test_dialog_button_follows_theme(stdscr, mock_win, monkeypatch):
    """High contrast theme adds reverse video to the dialog button."""
    monkeypatch.setattr(colors, "_active_theme", "high_contrast")
    mock_win.getch.side_effect = [ord("\n")]
    with (
        patch("curses.newwin", return_value=mock_win),
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ):
        message_dialog(stdscr, "Title", "Hello")
    button_calls = []
    for c in mock_win.addstr.call_args_list:
        if c.args[2] == "[ OK ]":
            button_calls.append(c)
    assert len(button_calls) == 1
    assert button_calls[0].args[3] & curses.A_REVERSE
