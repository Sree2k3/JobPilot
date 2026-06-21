"""
Job Matcher Agent — uses an LLM to score scraped jobs against a candidate's
combined profile.  Only jobs that pass the experience pre-filter reach here,
so the LLM can focus on skill/relevance quality rather than filtering.
"""

import logging
from typing import Optional

from .llm_client import call_llm_json, DEFAULT_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise job-matching analyst.  Score each job
listing against the candidate profile and return a JSON object with:

- `matches`: array of objects, each with:
  - `index`: int (position in the input jobs list, 0-based)
  - `match_score`: int 0-100 (overall relevance percentage)
  - `skill_match`: int 0-10 (how well the candidate's skills overlap with job skills)
  - `experience_fit`: str ("under-qualified" | "good-fit" | "over-qualified")
  - `location_match`: bool (does the job location overlap with candidate's location?)
  - `why_match`: str (10-20 word explanation tied to SPECIFIC profile details)
  - `recommendation`: str ("strong" | "moderate" | "weak")

Rules:
1. Strong (>=80): strong skill overlap, good experience fit, location matches.
2. Moderate (60-79): decent skill overlap, reasonable experience fit.
3. Weak (<60): partial skill overlap or significant experience mismatch.
4. SCORE EVERY JOB in the input — do not omit any.
5. Skill_match must reflect REAL overlap between job skills and candidate skills.
6. Location matches if the candidate's city appears in ANY location field.
7. Sort the matches array by match_score descending.
"""


def score_jobs(
    profile: dict,
    jobs: list[dict],
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """
    Score a list of scraped jobs against a candidate profile.

    Args:
        profile: The dict from CandidateProfile.combine().
        jobs: List of job dicts (should already be experience-filtered).
        model: OpenRouter model ID.

    Returns:
        Jobs enriched with match scores, sorted by relevance descending.
    """
    if not jobs:
        return []

    profile_summary = _profile_to_summary(profile)

    # Batch into chunks of 10
    batch_size = 10
    all_scored: list[dict] = []

    for batch_start in range(0, len(jobs), batch_size):
        batch = jobs[batch_start:batch_start + batch_size]
        jobs_summary = _jobs_to_text(batch)

        result = call_llm_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=(
                f"Candidate Profile:\n{profile_summary}\n\n"
                f"Job Listings (batch {batch_start}-{batch_start + len(batch) - 1}):\n"
                f"{jobs_summary}\n\n"
                f"Score each relevant job and return JSON."
            ),
            model=model,
            max_tokens=3000,
        )

        if result and "matches" in result and len(result["matches"]) > 0:
            for m in result["matches"]:
                idx = m.get("index") or m.get("job_index")
                if idx is None:
                    continue
                global_idx = batch_start + idx
                if 0 <= global_idx < len(jobs):
                    enriched = dict(jobs[global_idx])
                    enriched.update(
                        {
                            "match_score": m.get("match_score", 50),
                            "skill_match": m.get("skill_match", 5),
                            "experience_fit": m.get(
                                "experience_fit", "unknown"
                            ),
                            "location_match": m.get("location_match", False),
                            "why_match": m.get("why_match", ""),
                            "recommendation": m.get(
                                "recommendation", "moderate"
                            ),
                        }
                    )
                    all_scored.append(enriched)

    if all_scored:
        all_scored.sort(
            key=lambda x: x.get("match_score", 0), reverse=True
        )
        logger.info(
            "Matcher agent: scored %d jobs (top: %d%%)",
            len(all_scored),
            all_scored[0].get("match_score", 0) if all_scored else 0,
        )
        return all_scored

    logger.warning("LLM matching returned no relevant jobs")
    return []


def _profile_to_summary(profile: dict) -> str:
    """Condense a combined profile dict into a rich short text for the LLM."""
    lines = []
    if name := profile.get("full_name"):
        lines.append(f"Name: {name}")
    if title := profile.get("current_job_title"):
        lines.append(f"Current title: {title}")
    if exp := profile.get("total_experience_years"):
        lines.append(f"Experience: {exp}")
    if loc := profile.get("location") or profile.get("current_city"):
        lines.append(f"Location: {loc}")
    if roles := profile.get("preferred_roles"):
        lines.append(f"Preferred roles: {roles}")
    if mode := profile.get("work_mode"):
        lines.append(f"Work mode preference: {mode}")
    if emp := profile.get("employment_type"):
        lines.append(f"Employment type: {emp}")

    all_skills = profile.get("skills", [])
    tech_skills = profile.get("technical_skills", [])
    skills = tech_skills if tech_skills else all_skills
    if skills:
        lines.append(f"Skills: {', '.join(skills[:20])}")

    # Include project / experience context for richer matching
    exp_data = profile.get("work_experiences", [])
    if exp_data:
        latest = exp_data[0]
        lines.append(
            f"Latest experience: {latest.get('job_title', '')} @ "
            f"{latest.get('company', '')}"
        )
        desc = latest.get("description", "")
        if desc and len(desc) > 20:
            lines.append(f"Description: {desc[:300]}")

    if summary := profile.get("professional_summary"):
        lines.append(f"Summary: {summary[:400]}")

    return "\n".join(lines)


def _jobs_to_text(jobs: list[dict]) -> str:
    """Serialize a list of job dicts into numbered text for the LLM."""
    lines = []
    for i, j in enumerate(jobs):
        title = j.get("job_title", j.get("title", "?"))
        company = j.get("company", "?")
        exp = j.get("experience_required", j.get("experience", "?"))
        loc = j.get("location", "?")
        salary = j.get("salary", "Not listed")
        skills_raw = j.get("skills", [])
        skills_str = ", ".join(skills_raw[:10]) if isinstance(skills_raw, list) else str(skills_raw)
        lines.append(
            f"[{i}] Title: {title}\n"
            f"    Company: {company}\n"
            f"    Experience required: {exp}\n"
            f"    Location: {loc}\n"
            f"    Salary: {salary}\n"
            f"    Skills: {skills_str}\n"
        )
    return "\n".join(lines)
