"""
Test configuration shared by every group.

Deliberately light: it sets the environment the API is imported with, finds the
checkout, and registers the markers. The fixtures that need pandas or a trained
model live in ``tests/ml/conftest.py``, so a run of one group does not pay for
another group's dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path

# Set before anything imports the API, because settings are read at import
# time. conftest is loaded before any test module, which is what makes this
# the one place that has to say it.
os.environ.setdefault("SESSION_SECRET", "test-secret-not-used-in-production")
os.environ.setdefault("EAGER_MODEL_LOAD", "false")


def _project_root() -> Path:
    """
    The checkout, found by its marker file.

    Counting parent directories breaks the moment a test moves between
    folders, which is exactly what happened to the three tests that used to
    do it.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("could not find the project root above tests/")


#: The checkout. Tests that read a source file use this rather than counting
#: directories from their own location.
PROJECT_ROOT = _project_root()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: needs the real dataset or trained artifacts"
    )
