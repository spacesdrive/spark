"""
Reading, checking and writing user CSV files.

Every uploaded file is treated as hostile. It is never executed, never
unpickled, and never stored under the name the user chose. It is parsed as
text, checked column by column, and rejected with a sentence a person can act
on rather than a stack trace.

The column names Spark needs internally are terse (``Source``, ``Target``,
``Type``). Users should not have to know them, so this module accepts a set of
friendly aliases and maps them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.config.settings import settings
from api.types.dataset import ColumnIssue, DatasetError, ValidationResult
from api.utils.filenames import safe_stored_name, sanitize_display_name

#: What Spark calls a column, and what a user might call it.
COLUMN_ALIASES: Dict[str, List[str]] = {
    "Time": ["time", "timestamp", "created_at", "date", "datetime", "event_time",
             "transaction_time", "occurred_at"],
    "Source": ["source", "customer_id", "customer", "user_id", "account_id",
               "account", "payer", "card_id", "buyer_id"],
    "Target": ["target", "merchant_id", "merchant", "seller_id", "payee",
               "store_id", "recipient"],
    "Amount": ["amount", "value", "transaction_amount", "amt", "total", "price"],
    "Location": ["location", "country", "region", "city", "geo", "market"],
    "Type": ["type", "payment_type", "channel", "payment_channel", "method",
             "payment_method", "instrument", "instrument_type"],
    "Labels": ["labels", "label", "is_fraud", "fraud", "target_label", "outcome",
               "class", "y"],
    "transaction_id": ["transaction_id", "txn_id", "id", "order_id",
                       "payment_id", "reference"],
}

#: Columns without which scoring cannot happen at all.
REQUIRED = ["Time", "Source", "Target", "Amount"]

#: Columns Spark can do without, at a cost that is stated rather than hidden.
RECOMMENDED = ["Location", "Type"]

#: How each column is described to a user.
COLUMN_HELP: Dict[str, dict] = {
    "transaction_id": {
        "label": "Transaction ID",
        "requirement": "recommended",
        "why": "Identifies each row in the results you download. Spark "
               "generates one if it is missing.",
        "example": "txn_000123",
    },
    "Time": {
        "label": "Timestamp",
        "requirement": "required",
        "why": "Puts transactions in order so each one is scored using only "
               "what came before it.",
        "example": "2026-03-01T10:04:00Z or 1710000",
    },
    "Amount": {
        "label": "Amount",
        "requirement": "required",
        "why": "How much the transaction was for. Used directly, and compared "
               "against what this customer normally spends.",
        "example": "49.90",
    },
    "Source": {
        "label": "Customer ID",
        "requirement": "required",
        "why": "Groups transactions by who paid, which is how repeated "
               "behaviour and account age are measured.",
        "example": "cust_8813",
    },
    "Target": {
        "label": "Merchant ID",
        "requirement": "required",
        "why": "Groups transactions by who was paid. Many different customers "
               "hitting one merchant in a burst is the main ring signal.",
        "example": "merch_204",
    },
    "Location": {
        "label": "Location",
        "requirement": "recommended",
        "why": "One of the four links in the graph. If it is missing, every "
               "row is treated as one location and that link carries nothing.",
        "example": "IN-KA",
    },
    "Type": {
        "label": "Payment channel",
        "requirement": "recommended",
        "why": "One of the four links in the graph. If it is missing, every "
               "row is treated as one channel and that link carries nothing.",
        "example": "upi",
    },
    "Labels": {
        "label": "Label",
        "requirement": "optional",
        "why": "What actually happened afterwards: 1 for fraud, 0 for normal. "
               "Needed only if you want precision and recall measured.",
        "example": "0",
    },
}

#: Values accepted for the label column, and what they mean.
LABEL_TRUE = {"1", "1.0", "true", "yes", "fraud", "chargeback", "y", "t"}
LABEL_FALSE = {"0", "0.0", "false", "no", "legit", "legitimate", "normal", "n", "f"}
LABEL_UNKNOWN_VALUES = {"2", "2.0", "", "unknown", "none", "null", "na", "n/a", "?"}



# storage


def check_upload(filename: str, content: bytes) -> None:
    """Reject anything that is not a plausible CSV before parsing it."""
    if not content:
        raise DatasetError("That file is empty.", "Upload a CSV with a header row and at least one transaction.")
    if len(content) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes / (1024 * 1024)
        raise DatasetError(
            f"That file is larger than the {mb:.0f} MB limit.",
            "Split it into smaller files, or remove columns Spark does not use.",
        )
    if not sanitize_display_name(filename).lower().endswith(".csv"):
        raise DatasetError(
            "Only CSV files are accepted.",
            "Export your data as CSV and upload that. Excel and JSON are not "
            "supported.",
        )
    if b"\x00" in content[:8192]:
        raise DatasetError(
            "That file looks like a binary file, not a CSV.",
            "Make sure you are uploading the exported CSV and not a "
            "spreadsheet or an archive.",
        )
    try:
        content[:8192].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetError(
            "That file is not valid UTF-8 text.",
            "Re-export it as CSV with UTF-8 encoding.",
        ) from exc


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store_upload(content: bytes) -> Tuple[str, Path]:
    """Write the bytes to disk under a random name and return both."""
    stored = safe_stored_name()
    path = Path(settings.upload_dir) / stored
    path.write_bytes(content)
    return stored, path


def upload_path(stored_name: str) -> Path:
    """
    Resolve a stored filename inside the upload directory.

    The name always comes from the database, never from a request, but this
    still refuses anything that escapes the directory. Defence in depth costs
    two lines here.
    """
    root = Path(settings.upload_dir).resolve()
    p = (root / Path(stored_name).name).resolve()
    if not str(p).startswith(str(root)):
        raise DatasetError("That file could not be found.")
    return p


# parsing and validation


def read_csv(path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    """Read a CSV with a hard row cap, so a huge file cannot exhaust memory."""
    cap = max_rows or settings.max_test_rows
    try:
        df = pd.read_csv(path, nrows=cap + 1, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError as exc:
        raise DatasetError(
            "That file has no rows.", "Add a header row and at least one transaction."
        ) from exc
    except pd.errors.ParserError as exc:
        raise DatasetError(
            "That file could not be read as a CSV.",
            "Check that every row has the same number of commas, and that any "
            "text containing a comma is wrapped in quotes.",
        ) from exc
    if len(df) > cap:
        raise DatasetError(
            f"That file has more than {cap:,} rows.",
            f"Split it into files of {cap:,} rows or fewer.",
        )
    return df


def detect_mapping(columns: List[str]) -> Dict[str, str]:
    """Guess which of the user's columns is which. Case and spacing insensitive."""
    normalised = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in columns}
    mapping: Dict[str, str] = {}
    for spark_col, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = re.sub(r"[^a-z0-9]", "", alias)
            if key in normalised:
                mapping[spark_col] = normalised[key]
                break
    return mapping


def _bad_examples(series: pd.Series, mask: pd.Series, limit: int = 3) -> List[str]:
    vals = series[mask].astype(str).unique().tolist()
    return [v[:40] for v in vals[:limit]]


def validate(
    df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Check a parsed CSV and describe every problem in plain language."""
    columns = list(df.columns)
    mapping = mapping or detect_mapping(columns)
    mapping = {k: v for k, v in mapping.items() if v in columns}

    issues: List[ColumnIssue] = []
    notes: List[str] = []

    missing_required = [c for c in REQUIRED if c not in mapping]
    missing_recommended = [c for c in RECOMMENDED if c not in mapping]

    for col in missing_required:
        help_ = COLUMN_HELP[col]
        issues.append(
            ColumnIssue(
                column=help_["label"],
                problem=f"No column looks like {help_['label'].lower()}.",
                fix=(
                    f"Add a column named '{col}' (or one of: "
                    f"{', '.join(COLUMN_ALIASES[col][:4])}), or map an existing "
                    f"column to it below."
                ),
            )
        )
    for col in missing_recommended:
        help_ = COLUMN_HELP[col]
        issues.append(
            ColumnIssue(
                column=help_["label"],
                problem=f"No {help_['label'].lower()} column was found.",
                fix=help_["why"],
                severity="warning",
            )
        )

    if len(df) == 0:
        issues.append(
            ColumnIssue(
                column="file",
                problem="The file has a header but no transactions.",
                fix="Add at least one row of data below the header.",
            )
        )

    # amount must be numeric and not negative
    time_kind = "numeric"
    if "Amount" in mapping:
        raw = df[mapping["Amount"]]
        num = pd.to_numeric(raw.str.replace(",", "", regex=False), errors="coerce")
        bad = num.isna() & (raw.str.strip() != "")
        if bad.any():
            issues.append(
                ColumnIssue(
                    column=COLUMN_HELP["Amount"]["label"],
                    problem=f"{int(bad.sum()):,} rows have an amount that is not "
                            f"a number.",
                    fix="Remove currency symbols and thousands separators, so a "
                        "value reads like 1499.00 rather than Rs 1,499.00.",
                    examples=_bad_examples(raw, bad),
                )
            )
        empty = raw.str.strip() == ""
        if empty.any():
            issues.append(
                ColumnIssue(
                    column=COLUMN_HELP["Amount"]["label"],
                    problem=f"{int(empty.sum()):,} rows have no amount.",
                    fix="Fill in the amount, or remove those rows.",
                )
            )
        neg = num < 0
        if neg.any():
            issues.append(
                ColumnIssue(
                    column=COLUMN_HELP["Amount"]["label"],
                    problem=f"{int(neg.sum()):,} rows have a negative amount.",
                    fix="Spark scores payments, not refunds. Remove refund rows "
                        "or make the amount positive.",
                    severity="warning",
                )
            )

    # time must be sortable
    if "Time" in mapping:
        raw = df[mapping["Time"]]
        num = pd.to_numeric(raw, errors="coerce")
        if num.notna().all() and len(raw) > 0:
            time_kind = "numeric"
        else:
            parsed = pd.to_datetime(raw, errors="coerce", utc=True, format="mixed")
            bad = parsed.isna()
            if bad.all():
                issues.append(
                    ColumnIssue(
                        column=COLUMN_HELP["Time"]["label"],
                        problem="The timestamp column could not be read as "
                                "dates or as numbers.",
                        fix="Use an ISO date such as 2026-03-01T10:04:00Z, or a "
                            "plain increasing number.",
                        examples=_bad_examples(raw, bad),
                    )
                )
            elif bad.any():
                issues.append(
                    ColumnIssue(
                        column=COLUMN_HELP["Time"]["label"],
                        problem=f"{int(bad.sum()):,} rows have a timestamp that "
                                f"could not be read.",
                        fix="Use the same date format in every row, for example "
                            "2026-03-01T10:04:00Z.",
                        examples=_bad_examples(raw, bad),
                    )
                )
            time_kind = "datetime"
            notes.append(
                "Timestamps are converted to positions in a sequence, because "
                "that is what the model was trained on. Rows are sorted "
                "oldest first and then numbered."
            )

    # ids must not be blank
    for col in ("Source", "Target"):
        if col in mapping:
            raw = df[mapping[col]]
            empty = raw.str.strip() == ""
            if empty.any():
                issues.append(
                    ColumnIssue(
                        column=COLUMN_HELP[col]["label"],
                        problem=f"{int(empty.sum()):,} rows have no "
                                f"{COLUMN_HELP[col]['label'].lower()}.",
                        fix="Every transaction needs one. Use a placeholder id "
                            "if the real one is unavailable, and expect weaker "
                            "history signals for those rows.",
                    )
                )

    # duplicate transaction ids
    if "transaction_id" in mapping:
        raw = df[mapping["transaction_id"]]
        dupes = raw.duplicated() & (raw.str.strip() != "")
        if dupes.any():
            issues.append(
                ColumnIssue(
                    column=COLUMN_HELP["transaction_id"]["label"],
                    problem=f"{int(dupes.sum()):,} transaction IDs appear more "
                            f"than once.",
                    fix="Make each ID unique, or remove the column and let "
                        "Spark generate them.",
                    severity="warning",
                    examples=_bad_examples(raw, dupes),
                )
            )

    # labels
    has_labels = False
    label_counts: Dict[str, int] = {}
    if "Labels" in mapping:
        raw = df[mapping["Labels"]].astype(str).str.strip().str.lower()
        fraud = raw.isin(LABEL_TRUE)
        legit = raw.isin(LABEL_FALSE)
        unknown = raw.isin(LABEL_UNKNOWN_VALUES)
        bad = ~(fraud | legit | unknown)
        label_counts = {
            "fraud": int(fraud.sum()),
            "legitimate": int(legit.sum()),
            "unknown": int(unknown.sum()),
        }
        has_labels = bool(fraud.sum() + legit.sum())
        if bad.any():
            issues.append(
                ColumnIssue(
                    column=COLUMN_HELP["Labels"]["label"],
                    problem=f"{int(bad.sum()):,} rows have a label Spark does "
                            f"not recognise.",
                    fix="Use 1 for fraud and 0 for normal. Leave the cell empty "
                        "or use 2 if the outcome is still unknown.",
                    examples=_bad_examples(df[mapping["Labels"]], bad),
                )
            )
        if has_labels and fraud.sum() == 0:
            notes.append(
                "Your labels contain no fraud, so precision and recall cannot "
                "be measured. Spark will still score every row."
            )
    else:
        notes.append(
            "No label column was found. Spark can score these transactions, "
            "but it cannot measure how accurate those scores were."
        )

    preview = df.head(5).to_dict(orient="records")
    ok = not missing_required and not any(i.severity == "error" for i in issues)

    return ValidationResult(
        ok=ok,
        n_rows=len(df),
        columns=columns,
        mapping=mapping,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
        has_labels=has_labels,
        label_counts=label_counts,
        issues=issues,
        preview=preview,
        time_kind=time_kind,
        notes=notes,
    )


def to_spark_frame(
    df: pd.DataFrame, mapping: Dict[str, str]
) -> pd.DataFrame:
    """
    Turn a validated user CSV into the frame the pipeline expects.

    Time becomes a position in a sequence. The model's velocity windows are
    counted in transactions, not seconds, so a real timestamp is only used to
    establish the order.
    """
    out = pd.DataFrame(index=range(len(df)))

    amt = pd.to_numeric(
        df[mapping["Amount"]].str.replace(",", "", regex=False), errors="coerce"
    ).fillna(0.0)
    out["Amount"] = amt.clip(lower=0.0).astype(float)

    raw_time = df[mapping["Time"]]
    num = pd.to_numeric(raw_time, errors="coerce")
    if num.notna().all():
        order_key = num
    else:
        order_key = pd.to_datetime(
            raw_time, errors="coerce", utc=True, format="mixed"
        ).astype("int64", errors="ignore")
        order_key = pd.to_numeric(order_key, errors="coerce").fillna(0)
    out["_order"] = order_key.to_numpy()

    out["Source"] = df[mapping["Source"]].astype(str).replace("", "unknown")
    out["Target"] = df[mapping["Target"]].astype(str).replace("", "unknown")
    out["Location"] = (
        df[mapping["Location"]].astype(str).replace("", "unknown")
        if "Location" in mapping
        else "unknown"
    )
    out["Type"] = (
        df[mapping["Type"]].astype(str).replace("", "unknown")
        if "Type" in mapping
        else "unknown"
    )

    if "Labels" in mapping:
        raw = df[mapping["Labels"]].astype(str).str.strip().str.lower()
        lab = np.full(len(df), 2, dtype=int)
        lab[raw.isin(LABEL_TRUE).to_numpy()] = 1
        lab[raw.isin(LABEL_FALSE).to_numpy()] = 0
        out["Labels"] = lab
    else:
        out["Labels"] = 2

    if "transaction_id" in mapping:
        ids = df[mapping["transaction_id"]].astype(str)
        ids = ids.where(ids.str.strip() != "", pd.Series(
            [f"row_{i:06d}" for i in range(len(df))], index=ids.index
        ))
        out["transaction_id"] = ids
    else:
        out["transaction_id"] = [f"row_{i:06d}" for i in range(len(df))]

    out = out.sort_values("_order", kind="mergesort").reset_index(drop=True)
    out["Time"] = np.arange(len(out), dtype=np.int64)
    return out.drop(columns=["_order"])


def column_reference() -> List[dict]:
    """The table shown on the data format page. One source, so it cannot drift."""
    order = ["transaction_id", "Time", "Amount", "Source", "Target", "Location",
             "Type", "Labels"]
    return [
        {
            "column": c,
            "label": COLUMN_HELP[c]["label"],
            "requirement": COLUMN_HELP[c]["requirement"],
            "why": COLUMN_HELP[c]["why"],
            "example": COLUMN_HELP[c]["example"],
            "accepted_names": COLUMN_ALIASES[c][:6],
        }
        for c in order
    ]
