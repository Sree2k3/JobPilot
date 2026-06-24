# JobPilot – Job Scraper Module (Phase 3)

from .naukri.scraper import scrape_naukri
from .indeed.scraper import scrape_indeed
from .search_agent import search_for_candidate
from .llm_client import call_llm_json, DEFAULT_MODEL
from .email_sender import send_job_report, is_email_configured

__all__ = [
    "scrape_naukri",
    "scrape_indeed",
    "search_for_candidate",
    "call_llm_json",
    "DEFAULT_MODEL",
    "send_job_report",
    "is_email_configured",
]
