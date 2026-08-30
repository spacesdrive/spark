"""
What a checked CSV came back as.

Kept apart from the service that produces them so a router can name the shape
it is returning without importing pandas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class DatasetError(Exception):
    """A problem with the uploaded file, phrased for the person who uploaded it."""

    def __init__(self, message: str, fix: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.fix = fix

    def as_dict(self) -> dict:
        return {"message": self.message, "fix": self.fix}


@dataclass
class ColumnIssue:
    column: str
    problem: str
    fix: str
    severity: str = "error"  # error|warning
    examples: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "column": self.column,
            "problem": self.problem,
            "fix": self.fix,
            "severity": self.severity,
            "examples": self.examples,
        }


@dataclass
class ValidationResult:
    ok: bool
    n_rows: int
    columns: List[str]
    mapping: Dict[str, str]          # spark column -> the user's column name
    missing_required: List[str]
    missing_recommended: List[str]
    has_labels: bool
    label_counts: Dict[str, int]
    issues: List[ColumnIssue]
    preview: List[dict]
    time_kind: str                   # "numeric" | "datetime"
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "n_rows": self.n_rows,
            "columns": self.columns,
            "mapping": self.mapping,
            "missing_required": self.missing_required,
            "missing_recommended": self.missing_recommended,
            "has_labels": self.has_labels,
            "label_counts": self.label_counts,
            "issues": [i.as_dict() for i in self.issues],
            "preview": self.preview,
            "time_kind": self.time_kind,
            "notes": self.notes,
        }
