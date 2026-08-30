"""
Writing CSV that a spreadsheet will not execute.

Result files are downloaded and opened in Excel or Sheets, and the values in
them came from a user upload, so every cell is neutralised on the way out.
"""

from __future__ import annotations

import csv
import io
from typing import List


def csv_safe_cell(value) -> str:
    """
    Neutralise a cell that a spreadsheet would treat as a formula.

    A value starting with =, +, - or @ is executed by Excel and by Google
    Sheets when the file is opened. Since these values came from a user
    upload, a leading apostrophe is added so the cell is read as text.
    """
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def write_csv(rows: List[dict], columns: List[str]) -> str:
    """Render result rows as CSV text, escaping anything formula-shaped."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({c: csv_safe_cell(row.get(c)) for c in columns})
    return buf.getvalue()
