# JobPilot - Intake Fetch Module
"""
Fetches candidate intake data from the published Google Sheet CSV.
Supports both fresh fetch and incremental (only new rows).
"""

import os
import sys
import hashlib
import pandas as pd
from datetime import datetime
from pathlib import Path


def get_sheet_url():
    """Read SHEET_CSV_URL from environment (loaded via .env)."""
    url = os.getenv("SHEET_CSV_URL")
    if not url or "{YOUR_ID}" in url:
        print("[ERROR] SHEET_CSV_URL not set or still has placeholder.")
        print("   Edit .env and paste your real published CSV URL.")
        sys.exit(1)
    return url


def fetch_all(url=None):
    """Fetch all rows from the published Sheet CSV."""
    if url is None:
        url = get_sheet_url()

    try:
        df = pd.read_csv(url)
        print(f"  [OK] Fetched {len(df)} response(s)")
        return df
    except Exception as e:
        print(f"  [FAILED] Failed to fetch data: {e}")
        sys.exit(1)


def show_summary(df):
    """Print a clean summary of each response."""
    if df.empty:
        print("  [!] No data found in the sheet.")
        return

    for idx, row in df.iterrows():
        print(f"\n  {'='*56}")
        print(f"    RESPONSE #{idx + 1}")
        print(f"  {'='*56}")
        print(f"    Full Name        : {_g(row, 'Full Name')}")
        print(f"    Email            : {_g(row, 'Email Address')}")
        print(f"    Phone            : {_g(row, 'Phone Number')}")
        print(f"    City             : {_g(row, 'Current City / Location')}")
        print(f"    Current Job Title: {_g(row, 'Current Job Title / Designation')}")
        print(f"    Experience       : {_g(row, 'Total Years of Experience')}")
        print(f"    Company          : {_g(row, 'Current Company')}")
        print(f"    Notice Period    : {_g(row, 'Notice Period')}")
        print(f"    Preferred Roles  : {_g(row, 'Preferred Roles')}")
        print(f"    Preferred Locs   : {_g(row, 'Preferred Job Locations')}")
        print(f"    Employment Type  : {_g(row, 'Employment Type')}")
        print(f"    Work Mode        : {_g(row, 'Work Mode Preference')}")
        print(f"    Seniority        : {_g(row, 'Seniority Level')}")


def save_backup(df, directory="data/backups"):
    """Save a timestamped backup CSV."""
    os.makedirs(directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{directory}/intake_{timestamp}.csv"
    df.to_csv(filename, index=False)
    print(f"\n  [SAVED] Backup -> {filename}")
    return filename


def get_row_hash(row):
    """Generate a unique hash for a row (for dedup / incremental tracking)."""
    raw = "|".join(str(v) for v in row.values)
    return hashlib.sha256(raw.encode()).hexdigest()


def _g(row, col, default="-"):
    """Safe getter for DataFrame rows."""
    return row.get(col, default) if pd.notna(row.get(col)) else default
