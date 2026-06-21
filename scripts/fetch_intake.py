#!/usr/bin/env python3
"""
JobPilot – Phase 1: Fetch intake data from published Google Sheet (CSV)
Entry-point script. Run directly or via cron.

Usage:
    python scripts/fetch_intake.py
"""

import sys
from pathlib import Path

# Add project root to sys.path so we can import from src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.intake.fetcher import fetch_all, show_summary, save_backup
from config.settings import get_settings
from datetime import datetime


def main():
    settings = get_settings()

    print("=" * 60)
    print("  JOBPILOT – INTAKE DATA FETCHER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    df = fetch_all()

    if df.empty:
        print("  ℹ️ No data fetched.")
        return

    show_summary(df)
    save_backup(df, directory=str(settings["BACKUP_DIR"]))


if __name__ == "__main__":
    main()
