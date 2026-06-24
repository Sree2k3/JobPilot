#!/usr/bin/env python3
"""
Entry-point script for Phase 3 – Job Scraper Agents.

Usage:
    python scripts/scrape_jobs.py <keyword> --source naukri    [--pages N]
    python scripts/scrape_jobs.py <keyword> --source indeed   [--location CITY]
    python scripts/scrape_jobs.py "python developer" --source naukri --pages 3
    python scripts/scrape_jobs.py "python developer" --source indeed --location "Bangalore"
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="JobPilot Phase 3 – Job Scraper (Naukri / Indeed)"
    )
    parser.add_argument("keyword", help="Job search keyword")
    parser.add_argument(
        "--source",
        default="naukri",
        choices=["naukri", "indeed"],
        help="Job source (default: naukri)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Pages to scrape for Naukri (20 jobs/page, default: 3).",
    )
    parser.add_argument(
        "--location",
        default="India",
        help="Location filter for Indeed (default: India).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/scraped/)",
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  JOBPILOT - PHASE 3: JOB SCRAPER")
    print(f"  Source: '{args.source}'  Keyword: '{args.keyword}'")
    if args.source == "naukri":
        print(f"  Pages: {args.pages}")
    else:
        print(f"  Location: '{args.location}'")
    print(f"{'=' * 60}\n")

    if args.source == "naukri":
        from src.jobpilot.scraper.naukri.scraper import NaukriScraper

        scraper = NaukriScraper(
            output_dir=args.output,
            max_pages=args.pages,
        )
        jobs = scraper.scrape_keyword(args.keyword)
        scraper.save_results(jobs, label=args.keyword)

    else:
        from src.jobpilot.scraper.indeed.scraper import IndeedScraper

        scraper = IndeedScraper(output_dir=args.output)
        jobs = scraper.scrape_keyword(args.keyword, location=args.location)
        scraper.save_results(jobs, label=args.keyword)

    print(f"\n{'=' * 60}")
    print(f"  SCRAPING COMPLETE")
    print(f"  Total jobs scraped: {len(jobs)}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
