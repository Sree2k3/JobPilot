"""
Search Orchestrator — reads a candidate profile, generates keywords, runs
the Naukri and Indeed scrapers on DEDICATED threads (one per platform),
scores all jobs via the LLM matcher (parallel batches), and saves results.

Threading model:
  - Thread A: Naukri → iterates all keywords sequentially (1 Chrome at a time)
  - Thread B: Indeed → iterates all keywords sequentially (1 Playwright at a time)
  - Both threads run simultaneously → ~2x speedup, safe RAM usage
  - LLM scoring: parallel batches via ThreadPoolExecutor (handled by job_matcher)
  - Email: single-threaded (SMTP isn't thread-safe)

This gives ~2.5 min per candidate (down from ~3.5 min) with stable ~400MB RAM.
"""

import os
import csv
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from .keyword_gen import generate_keywords
from .naukri.scraper import NaukriScraper
from .indeed.scraper import IndeedScraper
from .job_matcher import score_jobs
from .llm_client import DEFAULT_MODEL
from .email_sender import send_job_report, send_no_jobs_notification, is_email_configured
from .experience_filter import prefilter_by_experience, parse_candidate_experience
from .sent_history import filter_new_jobs, mark_as_sent

logger = logging.getLogger(__name__)

# Shared CSV headers used by both Naukri and Indeed
CSV_HEADERS = [
    "source",
    "job_title",
    "company",
    "experience_required",
    "location",
    "salary",
    "skills",
    "application_link",
]

# Default config
DEFAULT_PAGES_PER_KEYWORD = 3


def get_current_sheet_entries() -> set[tuple[str, str]]:
    """
    Fetch the current Google Sheet and return ``{(email_lower, name_lower), ...}``
    for every row.

    This is used to ensure Phase 3 only processes people still on the sheet.
    """
    try:
        from src.jobpilot.intake.fetcher import fetch_all
        import pandas as pd

        df = fetch_all()

        def _safe_val(row, col_hint):
            """Get a value from a DataFrame row, matching by substring."""
            if col_hint in row.index:
                val = row[col_hint]
            else:
                cl = col_hint.strip().lower()
                matched = None
                for c in row.index:
                    if cl in c.strip().lower():
                        matched = c
                        break
                if matched is None:
                    return ""
                val = row[matched]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val).strip()

        entries: set[tuple[str, str]] = set()
        for _, row in df.iterrows():
            email = _safe_val(row, "Email Address").lower()
            name = _safe_val(row, "Full Name").lower()
            if email and name:
                entries.add((email, name))
        logger.info("Current sheet has %d entry/entries", len(entries))
        return entries
    except Exception as e:
        logger.warning("Could not fetch current sheet entries: %s", e)
        return set()


def search_for_candidate(
    profile: dict,
    profile_name: str = "candidate",
    model: str = DEFAULT_MODEL,
    max_pages_per_keyword: int = DEFAULT_PAGES_PER_KEYWORD,
    freshness_days: int = 7,
    output_dir: Optional[str] = None,
    recipient_email: Optional[str] = None,
) -> list[dict]:
    """
    Full agent workflow for one candidate — with PARALLEL scraping & scoring.

    1. LLM generates 3-6 search keywords from the profile.
    2. Naukri + Indeed scrapers run in parallel for all keywords.
    3. LLM scores all scraped jobs in parallel batches.
    4. Ranked results are saved as CSV + JSON to *output_dir*.

    Args:
        profile: Combined profile dict (from CandidateProfile.combine()).
        profile_name: Used in output filenames.
        model: OpenRouter model ID.
        max_pages_per_keyword: Pages to scrape per keyword (Naukri).
        freshness_days: Naukri freshness filter in days (default 7 = 1 week).
        output_dir: Where to save results (default: ``data/scraped/``).
        recipient_email: If set, send results via email.
        max_scrape_workers: Max parallel scrape threads (default 4).
                            Each thread may launch Chrome (RAM-heavy),
                            so cap at 3-4 for typical machines.

    Returns:
        List of scored job dicts, sorted by match_score descending.
    """
    if output_dir is None:
        from config.settings import get_settings
        output_dir = get_settings()["DATA_DIR"] / "scraped"
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in profile_name)

    # ── Step 1: Generate keywords ──
    print("\n  [Agent] Generating search keywords from profile...")
    keywords = generate_keywords(profile, model=model)
    if not keywords:
        print("  [Agent] No keywords generated — nothing to search.")
        return []

    print(f"  [Agent] Keywords: {keywords}")

    # ── For freshers, also add internship keywords ──
    is_fresher = False
    exp_raw = (profile.get("total_experience_years") or "").strip().lower()
    if exp_raw in ("fresher", "entry level", "entry", "student", "trainee", "intern", "0"):
        is_fresher = True

    if is_fresher:
        intern_kws = list(keywords)
        for kw in keywords:
            intern_kws.append(f"{kw} internship")
        intern_kws.append("internship")
        seen_kw: set[str] = set()
        keywords = []
        for kw in intern_kws:
            k = kw.strip().lower()
            if k not in seen_kw:
                seen_kw.add(k)
                keywords.append(k)
        keywords = keywords[:6]
        print(f"  [Agent] Fresher detected — added internship searches")
        print(f"  [Agent] Expanded keywords: {keywords}")

    # ── Step 2: Scrape — one thread for Naukri, one thread for Indeed ──
    print(f"\n  [Agent] Scraping {len(keywords)} keyword(s) — "
          f"Naukri (1 thread) + Indeed (1 thread) simultaneously")

    # Build scraper instances (lightweight — no browser open yet)
    candidate_location = profile.get("location") or profile.get("current_city") or "India"

    naukri_scraper = NaukriScraper(
        output_dir=output_dir,
        max_pages=max_pages_per_keyword,
        freshness_days=freshness_days,
    )
    indeed_scraper = IndeedScraper(output_dir=output_dir)

    all_jobs: list[dict] = []
    seen_links: set = set()
    lock = Lock()

    def _naukri_thread_worker() -> None:
        """Thread A: scrape all Naukri keywords sequentially (1 Chrome at a time)."""
        for kw in keywords:
            jobs = naukri_scraper.scrape_keyword(kw)
            unique = 0
            with lock:
                for j in jobs:
                    link = j.get("application_link", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        all_jobs.append(j)
                        unique += 1
                    elif not link:
                        all_jobs.append(j)
                        unique += 1
            print(f"  [Scraper] Naukri '{kw}': {len(jobs)} jobs, {unique} new")

    def _indeed_thread_worker() -> None:
        """Thread B: scrape all Indeed keywords sequentially (1 Playwright at a time)."""
        for kw in keywords:
            jobs = indeed_scraper.scrape_keyword(kw, location=candidate_location)
            unique = 0
            with lock:
                for j in jobs:
                    link = j.get("application_link", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        all_jobs.append(j)
                        unique += 1
                    elif not link:
                        all_jobs.append(j)
                        unique += 1
            print(f"  [Scraper] Indeed '{kw}': {len(jobs)} jobs, {unique} new")

    # Launch both threads simultaneously
    t1 = threading.Thread(target=_naukri_thread_worker, name="naukri-scraper")
    t2 = threading.Thread(target=_indeed_thread_worker, name="indeed-scraper")
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    if not all_jobs:
        print("\n  [Agent] No jobs found across any keywords.")
        if recipient_email:
            _send_no_jobs_email(recipient_email, profile_name)
        return []

    naukri_count = sum(1 for j in all_jobs if j.get("source") == "Naukri")
    indeed_count = sum(1 for j in all_jobs if j.get("source") == "Indeed")
    print(f"\n  [Agent] Total unique jobs scraped: {len(all_jobs)} "
          f"(Naukri: {naukri_count}, Indeed: {indeed_count})")

    # ── Step 3a: Pre-filter by experience ──
    candidate_exp = parse_candidate_experience(profile)
    if candidate_exp != (None, None):
        print(f"  [Filter] Candidate experience: {candidate_exp[0]}-{candidate_exp[1]} yrs")
        pre_filtered = prefilter_by_experience(profile, all_jobs)
        print(f"  [Filter] After experience check: {len(all_jobs)} -> {len(pre_filtered)} jobs kept")
        all_jobs = pre_filtered
    else:
        print(f"  [Filter] Candidate experience unknown — skipping pre-filter")

    if not all_jobs:
        print("\n  [Agent] No jobs passed the experience filter.")
        if recipient_email:
            _send_no_jobs_email(recipient_email, profile_name)
        return []

    # ── Step 3b: LLM match scoring (parallel batches) ──
    print(f"\n  [Agent] Scoring {len(all_jobs)} jobs against profile via LLM (parallel)...")
    scored = score_jobs(profile, all_jobs, model=model)

    # ── Step 4: Save results ──
    csv_path = output_dir / f"matched_{safe_name}_{ts}.csv"
    json_path = output_dir / f"matched_{safe_name}_{ts}.json"

    output_fields = CSV_HEADERS + [
        "match_score",
        "skill_match",
        "experience_fit",
        "location_match",
        "missing_skills",
        "why_match",
        "recommendation",
    ]

    # Compute missing skills per job
    candidate_skills_lower = _get_candidate_skill_set(profile)
    for job in scored:
        job_skills_raw = job.get("skills", [])
        if isinstance(job_skills_raw, list):
            job_skills = [s.strip().lower() for s in job_skills_raw]
        else:
            job_skills = [str(job_skills_raw).strip().lower()]
        missing = [
            s for s in job_skills
            if s and not _candidate_has_skill(candidate_skills_lower, s)
        ]
        job["missing_skills"] = "; ".join(missing[:10]) if missing else ""

    # Save CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        for job in scored:
            row = {h: job.get(h, "") for h in output_fields}
            writer.writerow(row)

    # Save JSON (full detail)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=2, ensure_ascii=False, default=str)

    # ── Summary ──
    strong = sum(1 for j in scored if j.get("recommendation") == "strong")
    moderate = sum(1 for j in scored if j.get("recommendation") == "moderate")

    print(f"\n{'=' * 60}")
    print(f"  SEARCH COMPLETE for {profile_name}")
    print(f"  Total jobs found: {len(scored)}")
    print(f"  Strong matches:   {strong}")
    print(f"  Moderate matches: {moderate}")
    print(f"  Saved to:")
    print(f"    CSV:  {csv_path.name}")
    print(f"    JSON: {json_path.name}")

    # ── Step 5: Email the candidate (skip already-sent jobs) ──
    if recipient_email:
        email_worthy = [j for j in scored if j.get("match_score", 0) >= 60 and j.get("recommendation") != "weak"]
        weak_count = len(scored) - len(email_worthy)
        if weak_count:
            print(f"  [Quality] Filtered out {weak_count} low-quality match(es) (score < 60 or weak)")
        scored = email_worthy

        jobs_to_send = filter_new_jobs(recipient_email, scored, name=profile_name)
        skipped = len(scored) - len(jobs_to_send)
        if skipped:
            print(f"\n  [History] Removed {skipped} previously sent job(s) — {len(jobs_to_send)} new job(s) to send")

        if not jobs_to_send:
            print(f"  [History] No new jobs to send — all already sent in previous runs")
            print(f"  [Email] Sending no-jobs notification to {recipient_email}...")
            sent = send_no_jobs_notification(
                recipient_email=recipient_email,
                candidate_name=profile_name,
            )
            if sent:
                print(f"  [Email] No-jobs notification sent!")
            else:
                print(f"  [Email] Could not send no-jobs notification (check SMTP settings in .env)")
        else:
            print(f"\n  [Email] Sending report to {recipient_email} ({len(jobs_to_send)} jobs)...")
            sent = send_job_report(
                recipient_email=recipient_email,
                candidate_name=profile_name,
                jobs=jobs_to_send,
            )
            if sent:
                print(f"  [Email] Report sent successfully!")
                sent_links = [j.get("application_link", "") for j in jobs_to_send if j.get("application_link")]
                mark_as_sent(recipient_email, sent_links, name=profile_name)
            else:
                print(f"  [Email] Could not send (check SMTP settings in .env)")
    else:
        print(f"  [Email] No email address provided -- skipping email")

    print(f"{'=' * 60}\n")

    return scored


# ── Helpers for missing-skills computation ──

def _get_candidate_skill_set(profile: dict) -> set[str]:
    """Return a lowercase set of ALL candidate skills (tech + general)."""
    skills = set()
    for key in ("skills", "technical_skills"):
        raw = profile.get(key, [])
        if isinstance(raw, list):
            for s in raw:
                if ":" in s:
                    parts = s.split(":", 1)
                    skills.add(parts[-1].strip().lower())
                else:
                    skills.add(s.strip().lower())

    for exp in profile.get("work_experiences", []):
        desc = exp.get("description", "")
        import re
        for lang in re.findall(r"\b(Python|Java|JavaScript|Go|Rust|C\+\+|C#|SQL|TypeScript)\b", desc, re.IGNORECASE):
            skills.add(lang.lower())

    return skills


def _candidate_has_skill(candidate_skills: set[str], job_skill: str) -> bool:
    """Check if the candidate has a skill (with partial matching for compound terms)."""
    job_skill = job_skill.strip().lower()

    if job_skill in candidate_skills:
        return True

    short_map = {
        "ml": "machine learning",
        "ai": "artificial intelligence",
        "nlp": "natural language processing",
        "cv": "computer vision",
        "llm": "large language models",
        "rag": "retrieval-augmented generation",
        "cnn": "convolutional neural network",
        "gen ai": "generative ai",
    }
    expanded = short_map.get(job_skill)
    if expanded and expanded in candidate_skills:
        return True

    for cs in candidate_skills:
        if job_skill in cs or cs in job_skill:
            return True

    return False


def _send_no_jobs_email(recipient_email: str, profile_name: str) -> None:
    """Send a no-jobs-found notification email (shared helper for early-exit paths)."""
    print(f"\n  [Email] Sending no-jobs notification to {recipient_email}...")
    sent = send_no_jobs_notification(
        recipient_email=recipient_email,
        candidate_name=profile_name,
    )
    if sent:
        print(f"  [Email] No-jobs notification sent!")
    else:
        print(f"  [Email] Could not send no-jobs notification (check SMTP settings in .env)")
