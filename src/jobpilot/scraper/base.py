"""
Base job scraper — abstract class that all platform scrapers inherit from.

Provides:
  - Shared CSV_HEADERS (single source of truth)
  - File-writing helpers (_write_csv, _save_json)
  - Thread-safe parallel keyword scraping (scrape_all with ThreadPoolExecutor)
  - Shared deduplication logic

Each subclass implements scrape_keyword() which must be THREAD-SAFE:
  - Create its OWN browser/driver resources per call
  - Accept a single keyword and return a list of job dicts
  - NOT write to shared state (return results instead)
"""

import csv
import json
import logging
import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ── Shared CSV schema (single source of truth) ──────────────────────────

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


# ── Helpers ─────────────────────────────────────────────────────────────

def _sanitize_filename(s: str) -> str:
    """Replace characters that are problematic in filenames."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in s).strip()


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write job rows to a CSV file (shared across scrapers)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _save_json(path: Path, data: list) -> None:
    """Write data as JSON (shared across scrapers)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _resolve_output_dir(output_dir: Optional[str] = None) -> Path:
    """Resolve the output directory, defaulting to ``data/scraped/``."""
    if output_dir is None:
        from config.settings import get_settings
        output_dir = get_settings()["DATA_DIR"] / "scraped"
    out = Path(output_dir)
    os.makedirs(out, exist_ok=True)
    return out


# ── Base class ──────────────────────────────────────────────────────────

class BaseJobScraper(ABC):
    """
    Abstract base for all job platform scrapers.

    Subclasses must set:
        SOURCE_NAME  (e.g. "Naukri", "Indeed")

    Subclasses must implement:
        scrape_keyword(keyword, **kwargs) -> list[dict]
    """

    SOURCE_NAME = ""  # Override in subclass

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = _resolve_output_dir(output_dir)

    # ── Abstract ──────────────────────────────────────────────────────

    @abstractmethod
    def scrape_keyword(self, keyword: str, **kwargs) -> list[dict]:
        """
        Scrape ONE keyword.  MUST be thread-safe:
          - Create own browser/driver resources (don't share across threads)
          - Return list[dict] matching CSV_HEADERS keys
          - Do NOT write to disk (caller handles save)
        """
        ...

    # ── Parallel scraper ──────────────────────────────────────────────

    def scrape_all(
        self,
        keywords: list[str],
        max_workers: int = 3,
        **kwargs,
    ) -> list[dict]:
        """
        Scrape multiple keywords in parallel using a thread pool.

        Each keyword runs in its own thread, each thread creates its own
        browser resources (thread-safe by design).

        Args:
            keywords: List of search terms.
            max_workers: Max concurrent threads (default 3).
                         Cap at 2 for RAM-heavy scrapers (Selenium/Chrome).
            **kwargs: Forwarded to scrape_keyword().

        Returns:
            List of job dicts deduplicated by application_link.
        """
        if not keywords:
            return []

        all_jobs: list[dict] = []
        seen_links: set = set()
        lock = Lock()

        def _scrape_one(kw: str) -> tuple[str, int, int]:
            """Scrape one keyword and return (keyword, total, unique)."""
            jobs = self.scrape_keyword(kw, **kwargs)
            unique_count = 0
            with lock:
                for j in jobs:
                    link = j.get("application_link", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        all_jobs.append(j)
                        unique_count += 1
                    elif not link:
                        all_jobs.append(j)
                        unique_count += 1
            return kw, len(jobs), unique_count

        results: list[tuple[str, int, int]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_scrape_one, kw): kw for kw in keywords}
            for future in as_completed(futures):
                kw = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(
                        "[%s] %s: %d jobs, %d new",
                        self.SOURCE_NAME, result[0], result[1], result[2],
                    )
                except Exception as e:
                    logger.error("[%s] %s failed: %s", self.SOURCE_NAME, kw, e)

        # Sort results to maintain consistent order (by keyword order)
        result_map = {r[0]: r for r in results}
        total_jobs = sum(r[1] for r in results)
        total_unique = len(all_jobs)
        logger.info(
            "[%s] scrape_all done: %d keywords, %d total, %d unique",
            self.SOURCE_NAME, len(keywords), total_jobs, total_unique,
        )

        return all_jobs

    # ── Save results ──────────────────────────────────────────────────

    def save_results(self, jobs: list[dict], label: str = "") -> tuple[Optional[Path], Optional[Path]]:
        """
        Save scraped jobs to CSV and JSON files.

        Args:
            jobs: List of job dicts.
            label: Extra label for filename (e.g. keyword name).

        Returns:
            (csv_path, json_path) or (None, None) if no jobs.
        """
        if not jobs:
            return None, None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = _sanitize_filename(label) if label else "jobs"
        source = self.SOURCE_NAME.lower()

        csv_path = self.output_dir / f"{source}_{safe_label}_{ts}.csv"
        json_path = self.output_dir / f"{source}_{safe_label}_{ts}.json"

        _write_csv(csv_path, jobs)
        _save_json(json_path, jobs)

        return csv_path, json_path
