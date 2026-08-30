"""
Names for files that came from a user.

The name the uploader chose is never used on disk. It is kept only to show
back to them, and only after being stripped of anything that could escape a
directory or confuse a shell.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

#: Everything outside this set is replaced before a name is stored or shown.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_stored_name(suffix: str = ".csv") -> str:
    """A random name for the file on disk. The user's name is never used."""
    return f"{secrets.token_hex(16)}{suffix}"


def sanitize_display_name(name: str) -> str:
    """A version of the user's filename that is safe to store and show."""
    base = Path(name or "upload.csv").name
    base = _SAFE_NAME.sub("_", base)
    return base[:120] or "upload.csv"
