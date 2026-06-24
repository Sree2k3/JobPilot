#!/usr/bin/env python3
"""
Entry-point script for testing the Indeed scraper standalone.

Usage:
    python scripts/indeed_test.py "python developer"
    python scripts/indeed_test.py "python developer" --location "Bangalore"
    python scripts/indeed_test.py "data scientist" --location "Mumbai" --visible
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.scraper.indeed.scraper import scrape_indeed


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="JobPilot – Indeed Scraper Test"
    )
    parser.add_argument("keyword", help="Job search keyword")
    parser.add_argument(
        "--location",
        default="India",
        help="Location filter (default: India)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/scraped/)",
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  JOBPILOT - INDEED SCRAPER TEST")
    print(f"  Keyword:  '{args.keyword}'")
    print(f"  Location:  '{args.location}'")
    print(f"{'=' * 60}\n")

    from src.jobpilot.scraper.indeed.scraper import IndeedScraper

    scraper = IndeedScraper(output_dir=args.output)
    jobs = scraper.scrape_keyword(args.keyword, location=args.location)
    scraper.save_results(jobs, label=args.keyword)

    print(f"\n{'=' * 60}")
    print(f"  SCRAPING COMPLETE")
    print(f"  Total Indeed jobs scraped: {len(jobs)}")
    if jobs:
        print(f"\n  Sample jobs:")
        for j in jobs[:5]:
            print(f"    - {j['job_title']} @ {j['company']} ({j['location']})")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
