"""
Small helpers so every CLI command prints the same way.
"""

from __future__ import annotations

import pandas as pd

WIDTH = 74


def rule(char: str = "=") -> str:
    return char * WIDTH


def header(title: str) -> None:
    print(f"\n{rule()}\n{title}\n{rule()}")


def section(title: str) -> None:
    print(f"\n{title}")


def table(df: pd.DataFrame, floats: str = "{:.4f}") -> None:
    if df is None or len(df) == 0:
        print("  (none)")
        return
    print(df.to_string(index=False, float_format=lambda v: floats.format(v)))


def kv(label: str, value, width: int = 22) -> None:
    print(f"{label + ':':<{width}} {value}")
