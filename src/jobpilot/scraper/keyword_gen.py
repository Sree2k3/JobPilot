"""
Keyword Generator Agent — uses an LLM to derive optimal Naukri search
queries from a candidate's combined profile data.
"""

import logging
from typing import Optional

from .llm_client import call_llm_json, DEFAULT_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a job-search keyword strategist.  Given a candidate's
profile (skills, preferred roles, experience, education), output a JSON object
with:

- `queries`: list of 3-6 search keywords/phrases for Naukri.com
  (e.g. "ai engineer", "python developer", "generative ai").
  Pick terms that cast a WIDE net — include broader category terms and
  specific skill terms so the scraper finds diverse listings.
- `rationale`: one sentence explaining why these terms were chosen.

Rules:
- If the candidate listed MULTIPLE preferred roles (e.g. "Ai developer, Python developer"),
  generate at least one keyword per role.
- Prefer 2-3 word phrases over single words.
- Include at least one general role-title term and one skill-specific term.
- Do NOT include location.
- Use all lowercase.
"""


def generate_keywords(
    profile: dict,
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """
    Generate 3 search keywords from a candidate's combined profile data.

    Args:
        profile: The dict from CandidateProfile.combine().
        model: OpenRouter model ID.

    Returns:
        List of 3 search keyword strings.  Falls back to the preferred_roles
        field if the LLM is unavailable.
    """
    # Build a compact profile summary for the LLM
    profile_summary = _profile_to_summary(profile)

    result = call_llm_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Generate search keywords for this candidate:\n\n{profile_summary}",
        model=model,
    )

    if result and "queries" in result and len(result["queries"]) > 0:
        logger.info(
            "Keyword agent: %s — %s",
            result["queries"],
            result.get("rationale", ""),
        )
        return result["queries"][:3]

    # Fallback: use the preferred_roles field verbatim
    fallback = _fallback_keywords(profile)
    logger.info("Keyword agent (fallback): %s", fallback)
    return fallback


def _profile_to_summary(profile: dict) -> str:
    """Condense a combined profile dict into a short text for the LLM."""
    lines = []

    if name := profile.get("full_name"):
        lines.append(f"Name: {name}")
    if title := profile.get("current_job_title"):
        lines.append(f"Current title: {title}")
    if exp := profile.get("total_experience_years"):
        lines.append(f"Experience: {exp}")
    if roles := profile.get("preferred_roles"):
        lines.append(f"Preferred role: {roles}")

    tech_skills = profile.get("technical_skills", [])
    all_skills = profile.get("skills", [])
    if tech_skills:
        lines.append(f"Technical skills: {', '.join(tech_skills[:15])}")
    elif all_skills:
        # Grab a mix — some tech keywords for the LLM to parse
        raw = [s for s in all_skills if len(s.split()) <= 4][:20]
        lines.append(f"Skills: {', '.join(raw)}")

    if summary := profile.get("professional_summary"):
        lines.append(f"Summary: {summary[:300]}")

    return "\n".join(lines)


def _fallback_keywords(profile: dict) -> list[str]:
    """Fallback keywords when the LLM is unavailable."""
    roles = (profile.get("preferred_roles") or "").strip()
    if roles:
        return [roles.lower()]

    title = (profile.get("current_job_title") or "").strip()
    if title:
        return [title.lower()]

    return ["entry level"]
