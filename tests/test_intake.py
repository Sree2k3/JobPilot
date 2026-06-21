"""Tests for the intake fetcher module."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.intake.fetcher import get_row_hash
import pandas as pd


def test_row_hash_consistency():
    """Same row data should produce the same hash."""
    row1 = pd.Series({"Name": "Alice", "Email": "alice@example.com"})
    row2 = pd.Series({"Name": "Alice", "Email": "alice@example.com"})
    assert get_row_hash(row1) == get_row_hash(row2)


def test_row_hash_different():
    """Different row data should produce different hashes."""
    row1 = pd.Series({"Name": "Alice", "Email": "alice@example.com"})
    row2 = pd.Series({"Name": "Bob", "Email": "bob@example.com"})
    assert get_row_hash(row1) != get_row_hash(row2)


def test_row_hash_handles_nan():
    """NaN values should not break hashing."""
    import numpy as np
    row = pd.Series({"Name": "Alice", "Email": np.nan})
    h = get_row_hash(row)
    assert isinstance(h, str) and len(h) == 64
