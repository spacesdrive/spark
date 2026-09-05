"""
Where the project is on disk.

Found by looking for the marker file rather than by counting parent
directories, so moving a script between folders cannot silently repoint it at
the wrong tree.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("could not find the project root: no pyproject.toml above ops/")


ROOT = project_root()
