"""
Run the held-out test.

    python -m spark.models.evaluate
"""

from __future__ import annotations

import sys

from ml.evaluation.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
