"""
Unit tests for truenas_tui/tui/forms.py.

Tests patch curses.curs_set and curses.color_pair to avoid requiring a terminal.
Dialog calls (input_dialog, confirm_dialog, etc.) inside forms are also patched.
"""

import curses
from unittest.mock import MagicMock, patch

import pytest

from truenas_tui.tui import HardExit
from truenas_tui.tui.forms import (
    BoolField,
    ChoiceField,
    Form,
    FormField,
    IntField,
    ListField,
    SectionField,
)


def _make_stdscr(rows=24, cols=80):
    win = MagicMock()
    win.getmaxyx.return_value = (rows, cols)
    return win


def _curses_patches():
    """Context managers that suppress curses initialization requirements."""
    return [
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
    ]


def test_collect_plain_field():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "hello")]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result == {"name": "hello"}


def test_collect_bool_field_true():
    stdscr = _make_stdscr()
    fields = [BoolField("flag", "Flag", value=True)]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["flag"] is True


def test_collect_bool_field_false():
    stdscr = _make_stdscr()
    fields = [BoolField("flag", "Flag", value=False)]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["flag"] is False


def test_collect_choice_field():
    stdscr = _make_stdscr()
    fields = [ChoiceField("proto", "Protocol", choices=["TCP", "UDP", "ICMP"], value=1)]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["proto"] == "UDP"


def test_collect_choice_field_empty_choices():
    stdscr = _make_stdscr()
    fields = [ChoiceField("proto", "Protocol", choices=[], value=0)]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["proto"] == ""


def test_collect_int_field_valid():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=1500)]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["mtu"] == 1500


def test_collect_int_field_zero():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=0)]
    form = Form(stdscr, "Test", fields)
    # value=0 → buf=['0'] → int('0') = 0
    result = form._collect()
    assert result["mtu"] == 0


def test_collect_int_field_invalid_string():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=0)]
    form = Form(stdscr, "Test", fields)
    # Manually corrupt the buffer to an invalid value
    form._field_bufs[0] = list("abc")
    result = form._collect()
    assert result["mtu"] == "abc"  # invalid; _validate will catch it


def test_collect_int_field_empty_buffer():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=0)]
    form = Form(stdscr, "Test", fields)
    form._field_bufs[0] = []  # cleared
    result = form._collect()
    assert result["mtu"] == 0  # empty str → 0


def test_collect_skips_section_field():
    stdscr = _make_stdscr()
    fields = [SectionField("", "Section"), FormField("name", "Name", "val")]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert "" not in result  # section key not included
    assert result == {"name": "val"}


def test_collect_list_field():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["a", "b", "c"])]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["items"] == ["a", "b", "c"]


def test_collect_list_field_empty():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=[])]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result["items"] == []


def test_collect_multiple_fields():
    stdscr = _make_stdscr()
    fields = [
        FormField("host", "Host", "nas1"),
        BoolField("dhcp", "DHCP", value=True),
        IntField("port", "Port", value=80),
    ]
    form = Form(stdscr, "Test", fields)
    result = form._collect()
    assert result == {"host": "nas1", "dhcp": True, "port": 80}


def test_validate_all_ok():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "hello")]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"name": "hello"})
    assert err == ""


def test_validate_int_below_min():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=100, min_val=68, max_val=9000)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"mtu": 50})
    assert err != ""
    assert "68" in err


def test_validate_int_above_max():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=100, min_val=68, max_val=9000)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"mtu": 9001})
    assert err != ""
    assert "9000" in err


def test_validate_int_not_an_int():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=0)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"mtu": "bad"})
    assert err != ""
    assert "whole number" in err.lower() or "number" in err.lower()


def test_validate_int_within_bounds():
    stdscr = _make_stdscr()
    fields = [IntField("mtu", "MTU", value=1500, min_val=68, max_val=9000)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"mtu": 1500})
    assert err == ""


def test_validate_custom_validator_returns_error():
    stdscr = _make_stdscr()

    def validator(v):
        return "Must not be empty" if not v else None

    fields = [FormField("name", "Name", "", validator=validator)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"name": ""})
    assert err == "Must not be empty"


def test_validate_custom_validator_passes():
    stdscr = _make_stdscr()

    def validator(v):
        return None

    fields = [FormField("name", "Name", "ok", validator=validator)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"name": "ok"})
    assert err == ""


def test_validate_skips_section_field():
    stdscr = _make_stdscr()
    fields = [SectionField("", "Section"), IntField("n", "N", value=5, min_val=1)]
    form = Form(stdscr, "Test", fields)
    err = form._validate({"n": 5})
    assert err == ""


def test_advance_forward_basic():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), FormField("b", "B", "")]
    form = Form(stdscr, "Test", fields)
    # n_items = 4 (2 fields + Save + Cancel)
    assert form._advance(0, +1) == 1
    assert form._advance(1, +1) == 2  # SAVE_IDX
    assert form._advance(2, +1) == 3  # CANCEL_IDX
    assert form._advance(3, +1) == 0  # wraps to field 0


def test_advance_backward_basic():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), FormField("b", "B", "")]
    form = Form(stdscr, "Test", fields)
    assert form._advance(1, -1) == 0
    assert form._advance(0, -1) == 3  # CANCEL_IDX (wraps)


def test_advance_skips_section_forward():
    stdscr = _make_stdscr()
    fields = [SectionField("", "Section"), FormField("name", "Name", "val")]
    form = Form(stdscr, "Test", fields)
    # Cancel (idx=3) advances +1 → wraps to 0 (SectionField), skips → 1 (FormField)
    assert form._advance(3, +1) == 1


def test_advance_skips_section_backward():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), SectionField("", "S"), FormField("b", "B", "")]
    form = Form(stdscr, "Test", fields)
    # From field b (idx=2), go backward: 1 is SectionField → skip → 0 (FormField a)
    assert form._advance(2, -1) == 0


def test_advance_wraps_around():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    # n_items = 3 (1 field + Save + Cancel)
    # From Cancel (2), +1 → 0 (FormField, not Section) → returns 0
    assert form._advance(2, +1) == 0


def test_field_y_offsets_plain_fields():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), FormField("b", "B", ""), FormField("c", "C", "")]
    form = Form(stdscr, "Test", fields)
    offsets = form._compute_field_y_offsets()
    assert offsets == [0, 1, 2]


def test_section_fields_take_two_rows():
    stdscr = _make_stdscr()
    fields = [SectionField("", "Section"), FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    offsets = form._compute_field_y_offsets()
    assert offsets[0] == 0  # SectionField starts at 0
    assert offsets[1] == 2  # FormField starts at 2 (Section takes 2 rows)


def test_mixed_field_y_offsets():
    stdscr = _make_stdscr()
    fields = [
        FormField("a", "A", ""),
        SectionField("", "S"),
        FormField("b", "B", ""),
    ]
    form = Form(stdscr, "Test", fields)
    offsets = form._compute_field_y_offsets()
    assert offsets[0] == 0  # FormField a
    assert offsets[1] == 1  # SectionField
    assert offsets[2] == 3  # FormField b (after SectionField which takes 2 rows)


def test_form_esc_returns_none():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "hello")]
    form = Form(stdscr, "Test", fields)
    stdscr.getch.side_effect = [27]  # Esc

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result is None


def test_form_ctrl_d_raises():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    stdscr.getch.side_effect = [4]  # Ctrl+D

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        with pytest.raises(HardExit):
            form.run()


def test_form_tab_advances_field():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), FormField("b", "B", "")]
    form = Form(stdscr, "Test", fields)
    # Tab twice → land on Save, Enter saves
    stdscr.getch.side_effect = [ord("\t"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"a": "", "b": ""}


def test_form_enter_save_valid():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "hello")]
    form = Form(stdscr, "Test", fields)
    # Tab to Save (SAVE_IDX=1), then Enter
    stdscr.getch.side_effect = [ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"name": "hello"}


def test_form_enter_save_with_validation_error():
    stdscr = _make_stdscr()

    def validator(v):
        return "Name is required" if not v else None

    fields = [FormField("name", "Name", "", validator=validator)]
    form = Form(stdscr, "Test", fields)
    # Tab → Save, Enter → fails validation
    # KEY_UP → back to field, type 'x', Tab → Save, Enter → succeeds
    stdscr.getch.side_effect = [
        ord("\t"),  # Tab → SAVE_IDX
        ord("\n"),  # Enter → validation fails (name is empty)
        curses.KEY_UP,  # UP → back to field 0
        ord("x"),  # type 'x'
        ord("\t"),  # Tab → SAVE_IDX
        ord("\n"),  # Enter → success
    ]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"name": "x"}


def test_form_cancel_button_returns_none():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "hello")]
    form = Form(stdscr, "Test", fields)
    # Tab, Tab → Cancel (CANCEL_IDX=2), Enter → returns None
    stdscr.getch.side_effect = [ord("\t"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result is None


def test_form_up_navigation():
    stdscr = _make_stdscr()
    fields = [FormField("a", "A", ""), FormField("b", "B", "")]
    form = Form(stdscr, "Test", fields)
    # Start at 0, Down → 1, Up → 0, Tab → 1, Tab → SAVE, Enter
    stdscr.getch.side_effect = [
        curses.KEY_DOWN,
        curses.KEY_UP,
        ord("\t"),
        ord("\t"),
        ord("\n"),
    ]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"a": "", "b": ""}


def test_form_bool_field_toggle():
    stdscr = _make_stdscr()
    fields = [BoolField("flag", "Flag", value=False)]
    form = Form(stdscr, "Test", fields)
    # Enter on BoolField toggles, Tab to Save, Enter saves
    stdscr.getch.side_effect = [ord("\n"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result["flag"] is True  # was False, toggled to True


def test_form_bool_space_toggle():
    stdscr = _make_stdscr()
    fields = [BoolField("flag", "Flag", value=True)]
    form = Form(stdscr, "Test", fields)
    # Space toggles bool
    stdscr.getch.side_effect = [ord(" "), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result["flag"] is False  # was True, toggled to False


def test_form_choice_field_arrow_cycle():
    stdscr = _make_stdscr()
    fields = [ChoiceField("proto", "Protocol", choices=["TCP", "UDP", "ICMP"], value=0)]
    form = Form(stdscr, "Test", fields)
    # KEY_RIGHT cycles forward in choices, Tab → Save, Enter
    stdscr.getch.side_effect = [curses.KEY_RIGHT, ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result["proto"] == "UDP"  # index 0 → 1 → 'UDP'


def test_text_field_typing():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    # Type 'h', 'i', Tab to Save, Enter
    stdscr.getch.side_effect = [ord("h"), ord("i"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"name": "hi"}


def test_text_field_backspace():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    stdscr.getch.side_effect = [
        ord("h"),
        ord("i"),
        curses.KEY_BACKSPACE,
        ord("\t"),
        ord("\n"),
    ]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"name": "h"}


def test_text_field_ctrl_u_clears():
    stdscr = _make_stdscr()
    fields = [FormField("name", "Name", "")]
    form = Form(stdscr, "Test", fields)
    stdscr.getch.side_effect = [
        ord("h"),
        ord("i"),
        21,
        ord("\t"),
        ord("\n"),
    ]  # Ctrl+U = 21

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"name": ""}


def test_int_field_rejects_non_digits():
    stdscr = _make_stdscr()
    fields = [IntField("num", "Num", value=5)]
    form = Form(stdscr, "Test", fields)
    # buf starts as ['5']. Type 'a' (rejected), Tab → Save, Enter
    stdscr.getch.side_effect = [ord("a"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"num": 5}  # 'a' was rejected


def test_int_field_accepts_digits():
    stdscr = _make_stdscr()
    fields = [IntField("num", "Num", value=0)]
    form = Form(stdscr, "Test", fields)
    # Ctrl+U to clear buf, type '4', '2', Tab → Save, Enter
    stdscr.getch.side_effect = [21, ord("4"), ord("2"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"num": 42}


def test_int_field_accepts_minus():
    stdscr = _make_stdscr()
    fields = [IntField("num", "Num", value=0)]
    form = Form(stdscr, "Test", fields)
    # Clear, type '-', '5', Tab → Save, Enter
    stdscr.getch.side_effect = [21, ord("-"), ord("5"), ord("\t"), ord("\n")]

    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form.run()
    assert result == {"num": -5}


def test_list_editor_esc_returns_list():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["x", "y"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [27]  # Esc → done
    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form._run_list_editor(0)
    assert result == ["x", "y"]


def test_list_editor_ctrl_d():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=[])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [4]  # Ctrl+D
    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        with pytest.raises(HardExit):
            form._run_list_editor(0)


def test_list_editor_add_item():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=[])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("a"), 27]  # 'a' add, Esc done
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value="new_item"),
    ):
        result = form._run_list_editor(0)
    assert result == ["new_item"]


def test_list_editor_add_cancelled():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=[])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("a"), 27]
    # input_dialog returns None (user cancelled)
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value=None),
    ):
        result = form._run_list_editor(0)
    assert result == []  # nothing added


def test_list_editor_delete_item():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["item1", "item2"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("d"), 27]  # 'd' delete, Esc done
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.confirm_dialog", return_value=True),
    ):
        result = form._run_list_editor(0)
    assert result == ["item2"]  # item1 (index 0) deleted


def test_list_editor_delete_cancelled():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["item1", "item2"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("d"), 27]
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.confirm_dialog", return_value=False),
    ):
        result = form._run_list_editor(0)
    assert result == ["item1", "item2"]  # unchanged


def test_list_editor_item_validator_reject():
    stdscr = _make_stdscr()

    def validator(val):
        return "Invalid value" if val == "bad" else None

    fields = [ListField("items", "Items", value=[], item_validator=validator)]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("a"), 27]
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value="bad"),
        patch("truenas_tui.tui.forms.message_dialog") as mock_msg,
    ):
        result = form._run_list_editor(0)
    assert result == []  # rejected
    mock_msg.assert_called_once()  # error dialog shown


def test_list_editor_item_validator_accept():
    stdscr = _make_stdscr()

    def validator(val):
        return None

    fields = [ListField("items", "Items", value=[], item_validator=validator)]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("a"), 27]
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value="good"),
    ):
        result = form._run_list_editor(0)
    assert result == ["good"]


def test_list_editor_edit_item():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["original"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("\n"), 27]  # Enter to edit, Esc done
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value="updated"),
    ):
        result = form._run_list_editor(0)
    assert result == ["updated"]


def test_list_editor_navigate_up_down():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["a", "b", "c"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [curses.KEY_DOWN, curses.KEY_DOWN, curses.KEY_UP, 27]
    with patch("curses.curs_set"), patch("curses.color_pair", return_value=0):
        result = form._run_list_editor(0)
    assert result == ["a", "b", "c"]  # unchanged, just navigated


def test_list_editor_uppercase_a():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=[])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("A"), 27]  # 'A' also adds
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.input_dialog", return_value="hello"),
    ):
        result = form._run_list_editor(0)
    assert result == ["hello"]


def test_list_editor_uppercase_d():
    stdscr = _make_stdscr()
    fields = [ListField("items", "Items", value=["x"])]
    form = Form(stdscr, "Test", fields)

    stdscr.getch.side_effect = [ord("D"), 27]  # 'D' also deletes
    with (
        patch("curses.curs_set"),
        patch("curses.color_pair", return_value=0),
        patch("truenas_tui.tui.forms.confirm_dialog", return_value=True),
    ):
        result = form._run_list_editor(0)
    assert result == []
