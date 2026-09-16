class HardExit(BaseException):
    """
    Raised when Ctrl+D is pressed anywhere in the TUI.

    Using BaseException (not Exception) means it propagates through all
    plugin/dialog call stacks without being caught by broad
    `except Exception:` handlers, and curses.wrapper's finally: block
    still restores the terminal before it surfaces in main().
    """


def format_error(exc: Exception) -> str:
    """
    Return a user-facing error string from an exception.

    Uses only the first non-empty line of the message so tracebacks and
    internal detail do not reach dialog boxes, capped at 200 characters.
    """
    msg = next((line.strip() for line in str(exc).splitlines() if line.strip()), "")
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return msg or type(exc).__name__
