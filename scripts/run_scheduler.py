"""
JobPilot Scheduler — runs the full pipeline on a configured weekly calendar.

When deployed on a 24/7 server, this loop:
  1. Checks the current day/time against a schedule (default: Mon & Thu at 09:00).
  2. When a scheduled slot fires, runs the entire pipeline:
       Phase 2: fetch intake -> download -> extract -> analyze -> profile JSONs
       Phase 3: for each candidate -> generate keywords -> scrape -> score -> email
  3. Logs every run attempt (success/failure + timestamps) to ``logs/scheduler.json``
     and ``data/sent_history/scheduler_calendar.json`` so you can audit without
     checking the server manually.

Usage (24/7 server):
    python scripts/run_scheduler.py          # runs forever, checking every 60s
    python scripts/run_scheduler.py --once   # run once and exit (for testing)

Schedule format is a list of (day_name, hour) pairs defined at the top of this
module.  The ``CALENDAR`` constant can be overridden via the env var
``SCHEDULE_CALENDAR`` as a JSON string::

    [["monday",9],["thursday",9]]
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────
#  DEFAULT CALENDAR — edit here to change the
#  weekly schedule before deploying.
# ─────────────────────────────────────────────
# Format: list of [day_name (lowercase), hour (0-23)]
DEFAULT_CALENDAR: list[list] = [
    ["monday", 9],     # Monday at 9:00 AM
    ["thursday", 9],   # Thursday at 9:00 AM
]

# How often the loop checks (seconds).  60 = once per minute.
CHECK_INTERVAL_SEC = 60

logger = logging.getLogger(__name__)


# ── Calendar helpers ─────────────────────────

def _load_calendar() -> list[tuple[str, int]]:
    """Load schedule from env var ``SCHEDULE_CALENDAR`` or fall back to default."""
    raw = os.getenv("SCHEDULE_CALENDAR", "")
    if raw:
        try:
            parsed = json.loads(raw)
            return [(entry[0].strip().lower(), int(entry[1])) for entry in parsed]
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            logger.warning("Invalid SCHEDULE_CALENDAR env var (%s), using default", e)
    return [(day, hour) for day, hour in DEFAULT_CALENDAR]


def _next_trigger(calendar: list[tuple[str, int]], now: Optional[datetime] = None) -> tuple[str, datetime]:
    """
    Find the next scheduled trigger time given the calendar and current time.

    Returns:
        ``(day_name, datetime_of_next_fire)``.
    """
    if now is None:
        now = datetime.now()

    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    candidates: list[tuple[str, datetime]] = []
    for day_name, hour in calendar:
        target_dow = day_map.get(day_name)
        if target_dow is None:
            continue
        days_ahead = target_dow - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.hour >= hour):
            days_ahead += 7
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        candidates.append((day_name, target))

    if not candidates:
        return ("unknown", now + timedelta(days=365))

    return min(candidates, key=lambda x: x[1])


def _is_trigger_time(calendar: list[tuple[str, int]], now: Optional[datetime] = None) -> bool:
    """Return True if *now* falls within a scheduled window (within the check interval)."""
    if now is None:
        now = datetime.now()

    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    current_dow = now.weekday()
    current_hour = now.hour
    current_minute = now.minute

    for day_name, hour in calendar:
        target_dow = day_map.get(day_name)
        if target_dow is None:
            continue
        if current_dow == target_dow and current_hour == hour and current_minute < 2:
            return True
    return False


# ── Run log ──────────────────────────────────

_RUN_LOG_PATH: Optional[Path] = None


def _get_run_log_path() -> Path:
    global _RUN_LOG_PATH
    if _RUN_LOG_PATH is None:
        from config.settings import get_settings
        log_dir = get_settings()["LOG_DIR"]
        log_dir.mkdir(parents=True, exist_ok=True)
        _RUN_LOG_PATH = log_dir / "scheduler.json"
    return _RUN_LOG_PATH


def _read_run_log() -> list[dict]:
    path = _get_run_log_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _append_run_log(entry: dict) -> None:
    path = _get_run_log_path()
    log = _read_run_log()
    log.append(entry)
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def _update_calendar_cache(next_fire: datetime) -> None:
    """Persist the next scheduled fire time so you can check without SSH."""
    path = _get_run_log_path().parent / "calendar_cache.json"
    data = {
        "next_scheduled_run": next_fire.isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Core scheduler ────────────────────────────

def run_scheduler(once: bool = False, name_filter: Optional[str] = None) -> None:
    """
    Main scheduler loop.

    Args:
        once: If True, run the pipeline immediately and exit (for testing).
              If False (default), loop forever checking the calendar.
        name_filter: If set, only process candidates whose name contains this string.
    """
    calendar = _load_calendar()
    day_names = ", ".join(f"{d} @ {h}:00" for d, h in calendar)
    print(f"\n{'='*60}")
    print(f"  JOBPILOT SCHEDULER")
    print(f"  Schedule: {day_names}")
    print(f"  Check interval: {CHECK_INTERVAL_SEC}s")
    if once:
        print(f"  Mode: ONE-SHOT (--once)")
    else:
        print(f"  Mode: 24/7 DAEMON")
    print(f"{'='*60}\n")

    if once:
        _execute_full_pipeline(name_filter=name_filter)
        return

    # ── Loop forever ──
    while True:
        now = datetime.now()

        # Show next trigger every hour
        if now.minute == 0:
            next_day, next_dt = _next_trigger(calendar, now)
            print(f"  [Clock] {now.strftime('%Y-%m-%d %H:%M')} — next run: {next_day} @ {next_dt.strftime('%Y-%m-%d %H:%M')}")
            _update_calendar_cache(next_dt)

        if _is_trigger_time(calendar, now):
            print(f"\n  [Clock] SCHEDULED TRIGGER at {now.strftime('%Y-%m-%d %H:%M')}")
            _execute_full_pipeline()
            # Sleep extra so we don't re-trigger within the same minute
            time.sleep(120)

        time.sleep(CHECK_INTERVAL_SEC)


def _execute_full_pipeline(name_filter: Optional[str] = None) -> dict:
    """
    Run the entire JobPilot pipeline for ALL candidates:
      1. Phase 2: parse_resumes pipeline (fetch sheet -> download -> extract -> analyze)
      2. Phase 3: for each profile -> search -> score -> email

    Args:
        name_filter: If set, only process candidates whose name contains this string.

    Returns a dict summarising the run (also appended to the run log).
    """
    start_time = datetime.now()
    print(f"\n{'#'*60}")
    print(f"  FULL PIPELINE RUN STARTED at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}\n")

    # ── Resolve project root (scripts/ -> Joblist/) ──
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    result = {
        "run_start": start_time.isoformat(),
        "phase2_profiles": 0,
        "phase2_skipped": 0,
        "phase3_candidates": 0,
        "phase3_total_jobs": 0,
        "phase3_strong": 0,
        "emails_sent": 0,
        "errors": [],
        "run_end": None,
        "success": False,
    }

    try:
        # ── Phase 2: Parse resumes ──
        print("\n--- Phase 2: Resume Parsing ---")
        from src.jobpilot.parser.pipeline import run_pipeline as phase2

        profiles = phase2(dedup_check=True)
        result["phase2_profiles"] = len(profiles)

        # Count skipped by dedup (profiles without parsed_resume = no-consent or dedup'd)
        # The pipeline's output already shows the skip count in print statements
        print(f"  Phase 2 complete: {len(profiles)} new profile(s) processed")

        # ── Phase 3: Search + email for each candidate ──
        print("\n--- Phase 3: Job Search Agents ---")
        from src.jobpilot.scraper.search_agent import search_for_candidate, get_current_sheet_entries
        from src.jobpilot.scraper.llm_client import DEFAULT_MODEL

        # Collect all profile JSONs
        profiles_dir = project_root / "data" / "profiles"
        candidates: list[tuple[str, str, dict]] = []
        for fpath in sorted(profiles_dir.glob("profile_*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            combined = data.get("combined") or {}
            form_data = data.get("form_data") or {}
            name = combined.get("full_name", fpath.stem)
            email = combined.get("email") or form_data.get("email") or ""
            candidates.append((name, email, combined))

        # Filter by name if --name was specified
        if name_filter:
            before = len(candidates)
            candidates = [
                (n, e, p) for n, e, p in candidates
                if name_filter.lower() in n.lower()
            ]
            filtered_out = before - len(candidates)
            if filtered_out:
                print(f"  Filtered out {filtered_out} candidate(s) not matching name '{name_filter}'")

        # Cross-reference against current sheet — only process active entries
        sheet_entries = get_current_sheet_entries()
        if sheet_entries:
            before = len(candidates)
            candidates = [
                (n, e, p) for n, e, p in candidates
                if (e.strip().lower(), n.strip().lower()) in sheet_entries
            ]
            skipped = before - len(candidates)
            if skipped:
                print(f"  Skipped {skipped} candidate(s) removed from the sheet")
        else:
            print("  [WARN] Could not fetch sheet entries — processing all profiles")

        result["phase3_candidates"] = len(candidates)
        print(f"  Found {len(candidates)} candidate(s) for Phase 3")

        for name, email, profile in candidates:
            print(f"\n  >>> Processing: {name} ({email})")
            try:
                jobs = search_for_candidate(
                    profile=profile,
                    profile_name=name,
                    model=DEFAULT_MODEL,
                    max_pages_per_keyword=2,
                    recipient_email=email if email else None,
                )
                result["phase3_total_jobs"] += len(jobs)
                result["phase3_strong"] += sum(1 for j in jobs if j.get("recommendation") == "strong")
                if jobs:
                    result["emails_sent"] += 1
            except Exception as e:
                err_msg = f"Failed for {name}: {e}"
                print(f"  [!] {err_msg}")
                result["errors"].append(err_msg)

        result["run_end"] = datetime.now().isoformat()
        result["success"] = True

        print(f"\n{'#'*60}")
        print(f"  FULL PIPELINE RUN COMPLETE")
        print(f"  Profiles: {result['phase2_profiles']}")
        print(f"  Candidates searched: {result['phase3_candidates']}")
        print(f"  Total jobs found: {result['phase3_total_jobs']}")
        print(f"  Emails sent: {result['emails_sent']}")
        print(f"{'#'*60}\n")

    except Exception as e:
        result["run_end"] = datetime.now().isoformat()
        result["success"] = False
        result["errors"].append(str(e))
        print(f"\n  [!!] Pipeline failed: {e}")

    # Save run log
    _append_run_log(result)
    return result


# ── CLI entry point ─────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="JobPilot 24/7 Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the full pipeline once and exit (for testing).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Only process candidates whose name contains this substring (e.g. --name Sreedhar).",
    )
    args = parser.parse_args()

    if args.name:
        # --name implies --once: run once for specific candidate(s)
        run_scheduler(once=True, name_filter=args.name)
    else:
        run_scheduler(once=args.once)
