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

    Takes only the first non-empty line of the exception message so that
    multi-line tracebacks or internal stack details are not exposed through
    dialog boxes.  Hard-capped at 200 characters to prevent dialog overflow.
    """
    msg = str(exc)
    for line in msg.splitlines():
        line = line.strip()
        if line:
            msg = line
            break
    if len(msg) > 200:
        msg = msg[:197] + '...'
    return msg or type(exc).__name__
