"""Limits shared by more than one schema."""

from __future__ import annotations

#: Longest an id from a caller may be. Applied to every free-text identifier so
#: a huge string cannot be used to push work onto the database.
MAX_ID_LEN = 128
