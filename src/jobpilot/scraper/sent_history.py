"""
Sent-job history tracker — prevents sending the same job listing to a
candidate more than once across different runs.

History is stored per email as a JSON file in ``data/sent_history/``.
Each file contains a list of ``application_link`` strings sent so far.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _history_path(email: str) -> Path:
    """Return the path to the history file for a candidate email."""
    from config.settings import get_settings
    data_dir = get_settings()["DATA_DIR"]
    history_dir = data_dir / "sent_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    safe_email = email.replace("@", "_at_").replace(".", "_dot_")
    return history_dir / f"{safe_email}.json"


def get_sent_links(email: str) -> set[str]:
    """
    Load all previously-sent application links for a given email.

    Args:
        email: Candidate's email address.

    Returns:
        Set of ``application_link`` strings already sent.
    """
    path = _history_path(email)
    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        links = data.get("sent_links", [])
        if isinstance(links, list):
            return set(links)
        return set()
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read sent history for %s: %s", email, e)
        return set()


def mark_as_sent(email: str, links: list[str]) -> None:
    """
    Persist a list of application links as sent for this candidate
    (merged with any existing history).

    Args:
        email: Candidate's email address.
        links: ``application_link`` strings from the jobs just sent.
    """
    path = _history_path(email)
    existing = get_sent_links(email)
    merged = existing | set(links)

    data = {
        "email": email,
        "updated_at": datetime.now().isoformat(),
        "total_sent": len(merged),
        "sent_links": sorted(merged),
    }

    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Sent-history updated for %s: %d total links", email, len(merged))
    except OSError as e:
        logger.error("Failed to write sent history for %s: %s", email, e)


def filter_new_jobs(email: str, jobs: list[dict]) -> list[dict]:
    """
    Remove jobs whose application_link has already been sent to this email.

    Args:
        email: Candidate's email address.
        jobs: List of scored job dicts (must have ``application_link`` key).

    Returns:
        Filtered list containing only jobs not yet sent.
    """
    sent_links = get_sent_links(email)
    if not sent_links:
        return jobs

    new_jobs = [j for j in jobs if j.get("application_link", "") not in sent_links]
    dropped = len(jobs) - len(new_jobs)

    if dropped > 0:
        logger.info("Sent-history: removed %d already-sent jobs for %s", dropped, email)

    return new_jobs
