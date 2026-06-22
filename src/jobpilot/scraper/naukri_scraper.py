"""
Naukri.com job scraper.

Uses Selenium with a real Chrome browser to search Naukri and extract
job listings. The scraper handles pagination and avoids bot detection by:
  - Running Chrome with stealth patches (no automation flags)
  - Setting a realistic user-agent and viewport
  - Waiting for JS-rendered content to fully load
  - Searching by direct URL navigation (works with SSR pages)

Selectors are based on Naukri's current DOM structure (class names
like .srp-jobtuple-wrapper, .title, .comp-name, etc.).
"""

import os
import csv
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────

SEARCH_BASE = "https://www.naukri.com/{keyword}-jobs"
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

# How many pages to scrape (20 jobs per page).
DEFAULT_MAX_PAGES = 5
# Freshness filter — only show jobs posted within this many days (Naukri param).
DEFAULT_FRESHNESS_DAYS = 7
# Selenium waits (seconds).
PAGE_LOAD_WAIT = 10
SCROLL_PAUSE = 1.5


# ── Helpers ──────────────────────────────────────────────────────────

def _sanitize_filename(s: str) -> str:
    """Replace characters that are problematic in filenames."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in s).strip()


def _job_tuple_script() -> str:
    """
    JavaScript snippet that extracts all job cards from the current page.
    Returns a JSON-serializable list of dicts.
    """
    return """
    var cards = document.querySelectorAll('.srp-jobtuple-wrapper');
    var results = [];
    cards.forEach(function(card) {
        var titleEl = card.querySelector('.title');
        var companyEl = card.querySelector('.comp-name');
        var expEl = card.querySelector('.exp-wrap');
        var locEl = card.querySelector('.loc-wrap');
        var linkEl = card.querySelector('a.title');
        var salaryEl = card.querySelector('.sal-wrap');
        var tags = [];
        card.querySelectorAll('.tag-li').forEach(function(t) {
            tags.push(t.innerText.trim());
        });
        results.push({
            title: titleEl ? titleEl.innerText.trim() : '',
            company: companyEl ? companyEl.innerText.trim() : '',
            experience: expEl ? expEl.innerText.trim() : '',
            location: locEl ? locEl.innerText.trim() : '',
            salary: salaryEl ? salaryEl.innerText.trim() : '',
            skills: tags,
            link: linkEl ? linkEl.href : '',
        });
    });
    return results;
    """


def _get_next_page_button_script() -> str:
    """JS to find and click the 'Next' pagination button, if present."""
    return """
    // Try multiple patterns for next-page buttons
    var selectors = [
        'a[href*="pageNo=' + (window.__nextPage || 2) + '"]',
        'a[class*="next"]',
        'a[class*="pageNo"]:last-child',
        'button[class*="next"]',
    ];
    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el) return el.href || '';
    }
    // Fallback: increment pageNo in current URL
    var match = window.location.href.match(/(pageNo=)(\\d+)/);
    if (match) {
        var next = parseInt(match[2]) + 1;
        return window.location.href.replace(/(pageNo=)(\\d+)/, '$1' + next);
    }
    return '';
    """


# ── Browser management ───────────────────────────────────────────────

def _create_driver() -> webdriver.Chrome:
    """
    Create a Chrome driver with stealth settings to reduce bot detection.
    Uses the USER's installed Chrome, NOT headless-mode (visible window),
    because Naukri's Akamai CDN blocks headless browsers.
    """
    options = Options()
    # Run in visible mode — Naukri blocks headless
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    # Remove the webdriver property that exposes automation
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
            """
        },
    )

    return driver


def _navigate_to_search(
    driver: webdriver.Chrome,
    keyword: str,
    page: int = 1,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> str:
    """
    Navigate to the Naukri search results page for a keyword.

    First visits the home page (to establish cookies for Akamai), then
    navigates to the search results.  For page > 1, appends the page param.
    Appends ``?freshness=N`` to filter by posting date (default 7 days).
    """
    keyword_slug = keyword.lower().replace(" ", "-").replace("--", "-")
    url = f"https://www.naukri.com/{keyword_slug}-jobs"
    if page > 1:
        url = f"https://www.naukri.com/{keyword_slug}-jobs-{page}"
    if freshness_days:
        url += f"?freshness={freshness_days}"

    driver.get(url)

    # Wait for job cards to render
    try:
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".srp-jobtuple-wrapper"))
        )
    except TimeoutException:
        logger.warning("Timeout waiting for job cards on %s", url)

    # Scroll down to trigger lazy loading
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, 600)")
        time.sleep(SCROLL_PAUSE)

    return url


# ── Core scraping ────────────────────────────────────────────────────

def scrape_naukri(
    keyword: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    output_dir: Optional[str] = None,
) -> list[dict]:
    """
    Scrape Naukri.com for job listings matching *keyword*.

    Args:
        keyword: Job search term (e.g. "ai", "python developer", "data scientist").
        max_pages: How many result pages to scrape (20 jobs/page).
        freshness_days: Only show jobs posted within this many days (Naukri param).
        output_dir: Directory to save CSV output.  Defaults to ``data/scraped/``.

    Returns:
        List of job dicts with keys matching CSV_HEADERS.
    """
    # ── Resolve output directory ──
    if output_dir is None:
        from config.settings import get_settings

        settings = get_settings()
        output_dir = settings["DATA_DIR"] / "scraped"
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # ── Timestamp ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_keyword = _sanitize_filename(keyword)

    # ── Launch browser ──
    logger.info("Launching browser for keyword='%s' (max %d pages)", keyword, max_pages)
    driver = _create_driver()

    all_jobs: list[dict] = []
    current_page = 1

    try:
        # Warm up: visit home page first for cookies
        logger.info("Visiting Naukri home page to establish session...")
        driver.get("https://www.naukri.com/")
        time.sleep(3)

        # Scrape each page
        for page_num in range(1, max_pages + 1):
            logger.info("Fetching page %d/%d ...", page_num, max_pages)
            actual_url = _navigate_to_search(driver, keyword, page=page_num, freshness_days=freshness_days)

            # Extract job cards
            page_jobs = driver.execute_script(_job_tuple_script())
            if not page_jobs:
                logger.info("  No jobs found on page %d — stopping", page_num)
                break

            logger.info("  Found %d job(s) on page %d", len(page_jobs), page_num)
            for j in page_jobs:
                j["source"] = "Naukri"
                j["job_title"] = j.pop("title")
                j["experience_required"] = j.pop("experience")
                j["application_link"] = j.pop("link")
                # Keep only the fields we want in CSV order
                all_jobs.append({h: j.get(h, "") for h in CSV_HEADERS})

            current_page = page_num

            # Check if there's a next page (stop gracefully)
            next_url = driver.execute_script(_get_next_page_button_script())
            if not next_url:
                logger.info("  No next page link found — stopping")
                break

    except WebDriverException as e:
        logger.error("Browser error: %s", e)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # ── Save results ──
    if all_jobs:
        csv_path = output_dir / f"naukri_{safe_keyword}_{ts}.csv"
        _write_csv(csv_path, all_jobs)
        logger.info("Saved %d jobs to %s", len(all_jobs), csv_path)

        json_path = output_dir / f"naukri_{safe_keyword}_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_jobs, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d jobs to %s", len(all_jobs), json_path)

    return all_jobs


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write job rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Naukri.com job scraper")
    parser.add_argument("keyword", help="Job search keyword (e.g. 'python developer')")
    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Number of pages to scrape (default: {DEFAULT_MAX_PAGES})",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/scraped/)",
    )
    parser.add_argument(
        "--freshness",
        type=int,
        default=DEFAULT_FRESHNESS_DAYS,
        help=f"Freshness in days (Naukri filter, default: {DEFAULT_FRESHNESS_DAYS})",
    )

    args = parser.parse_args()
    jobs = scrape_naukri(
        keyword=args.keyword,
        max_pages=args.pages,
        freshness_days=args.freshness,
        output_dir=args.output,
    )

    print(f"\nDone! Scraped {len(jobs)} job(s) for '{args.keyword}'")
