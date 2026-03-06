"""Unit tests for truenas_tui/tui/__init__.py — format_error() and HardExit."""
import pytest

from truenas_tui.tui import format_error, HardExit


# ---------------------------------------------------------------------------
# format_error()
# ---------------------------------------------------------------------------

def test_format_error_single_line():
    exc = ValueError("something went wrong")
    assert format_error(exc) == "something went wrong"


def test_format_error_multiline():
    exc = ValueError("first non-empty line\nsecond line\nthird line")
    assert format_error(exc) == "first non-empty line"


def test_format_error_empty_message():
    exc = ValueError("")
    # Empty message falls back to class name
    assert format_error(exc) == "ValueError"


def test_format_error_truncated():
    long_msg = "x" * 201
    exc = ValueError(long_msg)
    result = format_error(exc)
    assert len(result) == 200
    assert result.endswith("...")
    assert result[:197] == "x" * 197


def test_format_error_whitespace_lines():
    # Leading blank/whitespace lines are skipped; first real line is used
    exc = ValueError("\n   \nfirst real line\nsecond line")
    assert format_error(exc) == "first real line"


def test_format_error_strips_leading_whitespace():
    # Inline whitespace on a line is stripped
    exc = ValueError("  trimmed  ")
    assert format_error(exc) == "trimmed"


def test_format_error_exception_subclass():
    exc = RuntimeError("runtime issue")
    assert format_error(exc) == "runtime issue"


def test_format_error_exactly_200_chars():
    # Exactly 200 chars — should NOT be truncated
    msg = "a" * 200
    exc = ValueError(msg)
    result = format_error(exc)
    assert len(result) == 200
    assert not result.endswith("...")


# ---------------------------------------------------------------------------
# HardExit
# ---------------------------------------------------------------------------

def test_hard_exit_is_base_exception():
    assert isinstance(HardExit(), BaseException)


def test_hard_exit_is_not_exception():
    # HardExit must NOT be a subclass of Exception so that broad
    # `except Exception:` handlers do not swallow it.
    assert not isinstance(HardExit(), Exception)


def test_hard_exit_not_caught_by_except_exception():
    caught_by_exception = False
    caught_by_base = False
    try:
        raise HardExit()
    except Exception:
        caught_by_exception = True
    except BaseException:
        caught_by_base = True

    assert not caught_by_exception, "HardExit must not be caught by 'except Exception'"
    assert caught_by_base, "HardExit must be caught by 'except BaseException'"


def test_hard_exit_can_be_raised_and_caught():
    with pytest.raises(HardExit):
        raise HardExit()
