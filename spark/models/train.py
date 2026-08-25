"""
Train all models.

    python -m spark.models.train

Calls ml.training.train so there is one implementation, not two.
"""

from __future__ import annotations

import sys

from ml.training.train import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
