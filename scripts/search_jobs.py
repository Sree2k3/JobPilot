#!/usr/bin/env python3
"""
Entry-point script for the LLM-Powered Job Search Agent (Phase 3).

Usage:
    python scripts/search_jobs.py                         # Search for ALL candidates in data/profiles/
    python scripts/search_jobs.py --name "Sreekant"        # Search for a specific candidate by name
    python scripts/search_jobs.py --profile path/to.json   # Search from a raw profile JSON
    python scripts/search_jobs.py --model deepseek/deepseek-chat

    python scripts/search_jobs.py --pages 5               # More pages per keyword (default: 3)
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.scraper.search_agent import search_for_candidate, get_current_sheet_entries
from src.jobpilot.scraper.llm_client import DEFAULT_MODEL


def find_profiles(profiles_dir: Path) -> list[tuple[str, str, dict]]:
    """Find all profile JSONs in the profiles directory.

    Returns:
        List of (name, email, combined_dict) tuples.
    """
    results: list[tuple[str, str, dict]] = []
    for fpath in sorted(profiles_dir.glob("profile_*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [!]  Skipping {fpath.name}: {e}")
            continue

        combined = data.get("combined") or {}
        form_data = data.get("form_data") or {}
        name = combined.get("full_name", fpath.stem)
        email = combined.get("email") or form_data.get("email") or ""
        results.append((name, email, combined))
    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="JobPilot Phase 3 – LLM-Powered Job Search Agent"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Search for a specific candidate by name (substring match).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Path to a single profile JSON to search for.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenRouter model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Pages to scrape per keyword (20 jobs/page, default: 3).",
    )
    parser.add_argument(
        "--freshness",
        type=int,
        default=7,
        help="Naukri freshness filter in days (default: 7 = last week).",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  JOBPILOT - PHASE 3: LLM JOB SEARCH AGENT")
    print(f"  Model: {args.model}")
    print("=" * 60)

    # ── Load profile(s) ──
    profiles_dir = PROJECT_ROOT / "data" / "profiles"

    candidates: list[tuple[str, str, dict]] = []

    if args.profile:
        # Load a single explicit profile file
        fpath = Path(args.profile)
        if not fpath.exists():
            print(f"\n  [!]  Profile not found: {args.profile}")
            sys.exit(1)
        data = json.loads(fpath.read_text(encoding="utf-8"))
        combined = data.get("combined") or {}
        form_data = data.get("form_data") or {}
        name = combined.get("full_name", fpath.stem)
        email = combined.get("email") or form_data.get("email") or ""
        candidates.append((name, email, combined))
        print(f"\n  Loaded profile: {fpath.name} -> {name} ({email})")

    else:
        # Load all profiles
        candidates = find_profiles(profiles_dir)
        if not candidates:
            print("\n  No profiles found in data/profiles/")

        if args.name and candidates:
            # Filter by name
            name_lower = args.name.lower()
            candidates = [
                (n, e, p) for n, e, p in candidates if name_lower in n.lower()
            ]
            if not candidates:
                print(f"  No candidate matching '{args.name}'")
                sys.exit(1)

    print(f"  Candidates to process: {len(candidates)}\n")

    # ── Cross-reference against current sheet (skip removed entries) ──
    if not args.profile:
        sheet_entries = get_current_sheet_entries()
        if sheet_entries:
            before = len(candidates)
            candidates = [
                (n, e, p) for n, e, p in candidates
                if (e.strip().lower(), n.strip().lower()) in sheet_entries
            ]
            skipped = before - len(candidates)
            if skipped:
                print(f"  Skipped {skipped} candidate(s) not in current sheet\n")

    # ── Run search for each candidate ──
    all_results = {}
    for name, email, profile in candidates:
        print(f"\n{'#'*60}")
        print(f"  Processing: {name}")
        if email:
            print(f"  Email: {email}")
        print(f"{'#'*60}")

        results = search_for_candidate(
            profile=profile,
            profile_name=name,
            model=args.model,
            max_pages_per_keyword=args.pages,
            freshness_days=args.freshness,
            recipient_email=email if email else None,
        )
        all_results[name] = results

    # ── Final summary ──
    total_jobs = sum(len(v) for v in all_results.values())
    print(f"\n{'='*60}")
    print(f"  ALL DONE")
    print(f"  Candidates processed: {len(candidates)}")
    print(f"  Total jobs found:     {total_jobs}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
