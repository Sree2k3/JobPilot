"""
Experience pre-filter — parses experience-level text from both the
candidate profile and Naukri job listings, then hard-filters jobs
whose experience range doesn't overlap with the candidate's level.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Parse candidate experience ──

def parse_candidate_experience(profile: dict) -> tuple[Optional[int], Optional[int]]:
    """
    Determine the candidate's experience range (min, max) in years.

    Reads these fields in order of preference:
      1. ``total_experience_years`` — might be "Fresher", "0-1", "5+", "3"
      2. ``work_experiences`` — latest role's duration_years
      3. ``education`` — end_year tells us if still studying

    Returns:
        ``(min_years, max_years)`` or ``(None, None)`` if unknown.
    """
    raw = (profile.get("total_experience_years") or "").strip().lower()

    # -- Fresher / entry level --
    if raw in ("fresher", "entry level", "entry", "student", "trainee", "intern"):
        return (0, 1)

    # -- Numeric range --
    nums = re.findall(r"\d+", raw)
    if len(nums) >= 2:
        return (int(nums[0]), int(nums[1]))
    if len(nums) == 1:
        n = int(nums[0])
        return (n, n + 2)  # "3 years" → (3,5) to allow some range

    # -- Fallback: compute from work_experiences --
    exps = profile.get("work_experiences", [])
    if exps:
        total = 0
        for exp in exps:
            dur = exp.get("duration_years")
            if dur:
                total += dur
        if total > 0:
            return (max(0, int(total) - 1), int(total) + 1)

    # -- Check if still in education --
    edu = profile.get("education", [])
    if edu:
        # If latest education end_year is near-future, likely fresher
        last_end = edu[-1].get("end_year") if isinstance(edu[-1], dict) else None
        if last_end:
            try:
                if int(last_end) >= 2024:
                    return (0, 1)
            except (ValueError, TypeError):
                pass

    return (None, None)


# ── Parse job experience ──

def parse_job_experience(job: dict) -> tuple[Optional[int], Optional[int]]:
    """
    Extract the experience range from a job listing.

    Naukri formats: "0-2 Yrs", "2-5 Yrs", "5+ Yrs", "Fresher", "Entry Level".

    Returns:
        ``(min_years, max_years)`` or ``(None, None)`` if unparseable.
    """
    raw = (
        (job.get("experience_required") or job.get("experience") or "")
        .strip()
        .lower()
    )
    if not raw:
        return (None, None)

    # "Fresher" / "Entry Level" → (0, 1)
    if raw in ("fresher", "entry level", "entry", "0 yr"):
        return (0, 1)

    # Guard: must contain "yr" / "year" for a valid experience string.
    # Naukri sometimes puts walk-in dates ("24 Jun - 25 Jun") in the
    # experience field, which the regex would wrongly parse as 24-25 yrs.
    if "yr" not in raw and "year" not in raw:
        return (None, None)

    nums = re.findall(r"\d+", raw)
    if len(nums) >= 2:
        return (int(nums[0]), int(nums[1]))
    if len(nums) == 1:
        n = int(nums[0])
        # "5+ Yrs" → (5, 50) — open-ended "at least n years"
        if "+" in raw:
            return (n, 50)
        return (n, n)

    return (None, None)


def is_experience_match(
    candidate_range: tuple[Optional[int], Optional[int]],
    job_range: tuple[Optional[int], Optional[int]],
    tolerance: int = 2,
) -> bool:
    """
    Check whether the candidate's experience overlaps with the job's
    requirement within a *tolerance* in years.

    Examples (tolerance=2):
      Candidate (0,1) + Job (0-2)  → True
      Candidate (0,1) + Job (5-10) → False
      Candidate (3,5) + Job (2-5)  → True
      Candidate (3,5) + Job (6-9)  → True  (within tolerance)
      Candidate (3,5) + Job (10-15)→ False

    Args:
        candidate_range: ``(min, max)`` from ``parse_candidate_experience``.
        job_range: ``(min, max)`` from ``parse_job_experience``.
        tolerance: How many years beyond the job's max to still accept.

    Returns:
        ``True`` if the experience levels are compatible.
    """
    c_min, c_max = candidate_range
    j_min, j_max = job_range

    # If either is unknown, pass through (let LLM decide)
    if c_min is None or j_min is None:
        return True

    # Candidate's implied previous experience count (midpoint)
    c_mid = (c_min + c_max) / 2

    # --- Hard rules ---

    # 1. Fresher (0-1): job min MUST be 0 — strictly fresher-only roles
    if c_max <= 1:
        return j_min is not None and j_min == 0

    # 2. Job requires more than candidate's max + tolerance → reject
    if j_min is not None and j_min > c_max + tolerance:
        return False

    # 3. Overlap check: ranges must intersect
    if j_max is not None and j_max < c_min - tolerance:
        return False

    # 4. Midpoint check — skip for open-ended ranges ("5+ Yrs" → max=50)
    #    because the inflated max makes the midpoint meaningless.
    if j_max is not None and j_max < 30:  # only apply to well-bounded ranges
        j_mid = (j_min + j_max) / 2
        if j_mid > c_mid + tolerance + 1:
            return False

    return True


def prefilter_by_experience(
    profile: dict,
    jobs: list[dict],
    tolerance: int = 2,
) -> list[dict]:
    """
    Remove jobs whose experience requirement is incompatible with the
    candidate's experience level.

    Args:
        profile: Candidate combined profile dict.
        jobs: Scraped job listings.
        tolerance: Accepted deviation in years.

    Returns:
        Filtered list of jobs that pass the experience check.
    """
    candidate_exp = parse_candidate_experience(profile)
    if candidate_exp == (None, None):
        logger.info("Experience pre-filter: candidate experience unknown — passing all")
        return jobs

    c_label = f"{candidate_exp[0]}-{candidate_exp[1]} yrs"
    logger.info(
        "Experience pre-filter: candidate=%s, tolerance=%d, total_in=%d",
        c_label,
        tolerance,
        len(jobs),
    )

    kept = []
    dropped = 0
    for j in jobs:
        job_exp = parse_job_experience(j)
        if job_exp == (None, None):
            kept.append(j)  # let LLM decide if unparseable
            continue
        if is_experience_match(candidate_exp, job_exp, tolerance):
            kept.append(j)
        else:
            dropped += 1

    logger.info(
        "Experience pre-filter: kept=%d, dropped=%d (candidate=%s)",
        len(kept),
        dropped,
        c_label,
    )
    return kept
