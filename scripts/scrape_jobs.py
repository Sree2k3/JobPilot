#!/usr/bin/env python3
"""
Entry-point script for Phase 3 – Job Scraper Agents.

Usage:
    python scripts/scrape_jobs.py <keyword> [--pages N] [--output DIR]
    python scripts/scrape_jobs.py "python developer" --pages 3
    python scripts/scrape_jobs.py "ai engineer" --output data/my_scraped
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.scraper.naukri_scraper import scrape_naukri


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="JobPilot Phase 3 – Scrape jobs from Naukri.com"
    )
    parser.add_argument("keyword", help="Job search keyword")
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Number of result pages to scrape (20 jobs/page, default: 5)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/scraped/)",
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  JOBPILOT - PHASE 3: NAUKRI SCRAPER")
    print(f"  Keyword: '{args.keyword}'  Pages: {args.pages}")
    print(f"{'=' * 60}\n")

    jobs = scrape_naukri(
        keyword=args.keyword,
        max_pages=args.pages,
        output_dir=args.output,
    )

    print(f"\n{'=' * 60}")
    print(f"  SCRAPING COMPLETE")
    print(f"  Total jobs scraped: {len(jobs)}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
