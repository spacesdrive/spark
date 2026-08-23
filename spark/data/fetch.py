"""
Download the public S-FFSD dataset.

    python -m spark.data.fetch

The file is small and needs no login, which is why this project can be cloned
and run by anyone. It is a simulated dataset. See
docs/using-spark/dataset.md for what that means for the results.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

from ml.config import RAW_CSV, RAW_DIR

SOURCE_URL = "https://github.com/AI4Risk/antifraud/raw/main/data/S-FFSD.zip"
MEMBER = "S-FFSD.csv"


def fetch(url: str = SOURCE_URL, dest: Path = RAW_CSV, force: bool = False) -> Path:
    """Download and extract S-FFSD.csv into data/raw/."""
    dest = Path(dest)
    if dest.exists() and not force:
        print(f"[fetch] already present: {dest} ({dest.stat().st_size:,} bytes)")
        return dest

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] downloading {url}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        payload = resp.read()
    print(f"[fetch] received {len(payload):,} bytes")

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if MEMBER not in names:
            raise RuntimeError(f"{MEMBER} not found in archive; contains {names}")
        with zf.open(MEMBER) as src, open(dest, "wb") as out:
            out.write(src.read())

    print(f"[fetch] wrote {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download the public S-FFSD dataset.")
    ap.add_argument("--url", default=SOURCE_URL)
    ap.add_argument("--force", action="store_true", help="re-download if present")
    args = ap.parse_args(argv)
    try:
        fetch(args.url, force=args.force)
    except Exception as exc:  # network failures should not print a traceback
        print(f"[fetch] failed: {exc}", file=sys.stderr)
        print(
            "\nManual fallback:\n"
            f"  1. download {SOURCE_URL}\n"
            f"  2. unzip it and place S-FFSD.csv in {RAW_DIR}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
