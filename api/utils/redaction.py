"""
Taking things out of a message before a user is allowed to see it.

Server filesystem paths in particular: they tell the user nothing they can act
on, and tell an attacker where things live.
"""

from __future__ import annotations

import re


#: Anything that looks like a filesystem path. A training failure raised deep
#: inside pandas or torch routinely carries one, and job errors are shown in
#: the browser, so the message is scrubbed before it is ever stored.
_PATH = re.compile(
    r"""(?:[A-Za-z]:[\\/]|/)[^\s'"]*""",   # /opt/spark/... or C:\Users\...
)


def safe_error(exc: BaseException) -> str:
    """
    A failure message safe to show a user.

    The exception type and its text are kept, because they are what makes the
    message useful. Every path inside it is replaced, because a path tells the
    user nothing they can act on and tells an attacker where things live. The
    full traceback still goes to the server log.
    """
    message = _PATH.sub("[path]", str(exc)).strip()
    if len(message) > 400:
        message = message[:397] + "..."
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
