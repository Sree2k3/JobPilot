"""
Naukri.com job scraper.

Uses Playwright (headless) to search Naukri and extract job listings.
The scraper handles pagination and avoids bot detection by:
  - Using Playwright headless mode (undetectable — Naukri's Akamai CDN
    blocks Selenium headless but Playwright headless works fine)
  - Setting a realistic user-agent and viewport
  - Waiting for JS-rendered content to fully load
  - Searching by direct URL navigation (works with SSR pages)

Each scrape_keyword() call creates its OWN Playwright browser instance,
making it thread-safe for use with ThreadPoolExecutor or threading.

Selectors are based on Naukri's current DOM structure (class names
like .srp-jobtuple-wrapper, .title, .comp-name, etc.).
"""

import logging
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from ..base import BaseJobScraper, CSV_HEADERS

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────────

# How many pages to scrape per keyword call (20 jobs per page).
DEFAULT_MAX_PAGES = 3
# Freshness filter — only show jobs posted within this many days (Naukri param).
DEFAULT_FRESHNESS_DAYS = 7
# Playwright waits (milliseconds).
PAGE_LOAD_TIMEOUT = 30000
WAIT_TIMEOUT = 15000
SCROLL_WAIT_MS = 1500


# ── JS extractors ────────────────────────────────────────────────────────

def _job_tuple_script() -> str:
    """JavaScript arrow function to extract all job cards from the current page."""
    return """
    () => {
        const cards = document.querySelectorAll('.srp-jobtuple-wrapper');
        const results = [];
        cards.forEach(card => {
            const titleEl = card.querySelector('.title');
            const companyEl = card.querySelector('.comp-name');
            const expEl = card.querySelector('.exp-wrap');
            const locEl = card.querySelector('.loc-wrap');
            const linkEl = card.querySelector('a.title');
            const salaryEl = card.querySelector('.sal-wrap');
            const tags = [];
            card.querySelectorAll('.tag-li').forEach(t => {
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
    }
    """


def _get_next_page_button_script() -> str:
    """JS arrow function to find the 'Next' pagination button, if present."""
    return """
    () => {
        const selectors = [
            'a[href*="pageNo=' + (window.__nextPage || 2) + '"]',
            'a[class*="next"]',
            'a[class*="pageNo"]:last-child',
            'button[class*="next"]',
        ];
        for (let i = 0; i < selectors.length; i++) {
            const el = document.querySelector(selectors[i]);
            if (el) return el.href || '';
        }
        const match = window.location.href.match(/(pageNo=)(\\d+)/);
        if (match) {
            const next = parseInt(match[2]) + 1;
            return window.location.href.replace(/(pageNo=)(\\d+)/, '$1' + next);
        }
        return '';
    }
    """


# ── Scraper class ────────────────────────────────────────────────────────

class NaukriScraper(BaseJobScraper):
    """
    Thread-safe Naukri.com scraper (Playwright-based).

    Each call to scrape_keyword() launches its own headless Playwright
    browser, scrapes the configured number of pages, then quits.  This
    makes it safe to call from multiple threads.

    Usage:
        scraper = NaukriScraper()
        jobs = scraper.scrape_keyword("python developer")
        jobs = scraper.scrape_all(["python", "java", "go"], max_workers=3)
    """

    SOURCE_NAME = "Naukri"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    ):
        super().__init__(output_dir)
        self.max_pages = max_pages
        self.freshness_days = freshness_days

    # ── Browser ──────────────────────────────────────────────────────

    @staticmethod
    def _create_browser():
        """
        Create a Playwright browser+context with stealth-friendly defaults.

        Playwright's headless mode is significantly harder to detect than
        Selenium's — no automation flags leak, no webdriver property,
        realistic navigator APIs by default.
        """
        p = sync_playwright().start()
        # NOTE: Naukri's Akamai CDN blocks ALL headless browsers (both
        # Selenium and Playwright).  We must run visible mode.
        # Playwright's visible mode is still ~4x lighter than Selenium's.
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        return p, browser, context

    def _navigate_to_search(
        self,
        page,
        keyword: str,
        page_num: int = 1,
    ) -> str:
        """Navigate to the Naukri search results page for a keyword."""
        keyword_slug = keyword.lower().replace(" ", "-").replace("--", "-")
        url = f"https://www.naukri.com/{keyword_slug}-jobs"
        if page_num > 1:
            url = f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}"
        if self.freshness_days:
            url += f"?freshness={self.freshness_days}"

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        except PlaywrightTimeout:
            logger.warning("[Naukri] Timeout loading %s", url)

        # Wait for job cards to appear
        try:
            page.wait_for_selector(
                ".srp-jobtuple-wrapper",
                timeout=WAIT_TIMEOUT,
            )
        except PlaywrightTimeout:
            logger.warning("[Naukri] Timeout waiting for job cards on %s", url)

        # Scroll down to trigger lazy loading
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(SCROLL_WAIT_MS)

        return url

    # ── Core scrape (thread-safe) ────────────────────────────────────

    def scrape_keyword(self, keyword: str, **kwargs) -> list[dict]:
        """
        Scrape Naukri for ONE keyword.  Thread-safe.

        Each call creates its own Playwright browser instance, scrapes
        ``self.max_pages`` pages, then quits.

        Returns:
            List of job dicts matching CSV_HEADERS keys.
        """
        max_pages = kwargs.get("max_pages", self.max_pages)

        logger.info(
            "[Naukri] Launching Playwright for '%s' (%d pages)",
            keyword, max_pages,
        )

        p = None
        browser = None
        all_jobs: list[dict] = []

        try:
            p, browser, context = self._create_browser()
            page = context.new_page()
            page.set_default_timeout(PAGE_LOAD_TIMEOUT)

            # Warm up: visit home page first for cookies
            logger.info("[Naukri] Visiting home page to establish session...")
            try:
                page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
            except PlaywrightTimeout:
                logger.warning("[Naukri] Timeout on home page")

            # Scrape each page
            for page_num in range(1, max_pages + 1):
                self._navigate_to_search(page, keyword, page_num=page_num)

                # Extract job cards via JS (same as before)
                page_jobs = page.evaluate(_job_tuple_script())

                if not page_jobs:
                    logger.info("[Naukri] No jobs on page %d — stopping", page_num)
                    break

                logger.info("[Naukri] %d jobs on page %d", len(page_jobs), page_num)
                for j in page_jobs:
                    all_jobs.append({
                        "source": "Naukri",
                        "job_title": (j.get("title") or "").strip(),
                        "company": (j.get("company") or "").strip(),
                        "experience_required": (j.get("experience") or "").strip(),
                        "location": (j.get("location") or "").strip(),
                        "salary": (j.get("salary") or "").strip(),
                        "skills": j.get("skills", []),
                        "application_link": (j.get("link") or "").strip(),
                    })

                # Check for next page
                next_url = page.evaluate(_get_next_page_button_script())
                if not next_url:
                    break

            page.close()

        except Exception as e:
            logger.error("[Naukri] Unexpected error: %s", e)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if p:
                try:
                    p.stop()
                except Exception:
                    pass

        return all_jobs


# ── Module-level convenience function (backwards-compatible) ─────────────

# Re-export CSV_HEADERS for backwards compatibility
from ..base import CSV_HEADERS as NAUKRI_CSV_HEADERS

__all__ = [
    "NaukriScraper",
    "scrape_naukri",
    "CSV_HEADERS",
]

CSV_HEADERS = NAUKRI_CSV_HEADERS


def scrape_naukri(
    keyword: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    output_dir: Optional[str] = None,
) -> list[dict]:
    """
    Convenience function: create a NaukriScraper, scrape one keyword,
    save results, return jobs.

    This preserves the original function signature for backwards
    compatibility with scripts/search_jobs.py etc.

    Args:
        keyword: Job search term.
        max_pages: Pages to scrape (20 jobs per page).
        freshness_days: Freshness filter in days.
        output_dir: Output directory (default: data/scraped/).

    Returns:
        List of job dicts.
    """
    scraper = NaukriScraper(
        output_dir=output_dir,
        max_pages=max_pages,
        freshness_days=freshness_days,
    )
    jobs = scraper.scrape_keyword(keyword)
    scraper.save_results(jobs, label=keyword)
    return jobs


# ── CLI entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Naukri.com job scraper")
    parser.add_argument("keyword", help="Job search keyword")
    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Pages to scrape (default: {DEFAULT_MAX_PAGES})",
    )
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument(
        "--freshness",
        type=int,
        default=DEFAULT_FRESHNESS_DAYS,
        help=f"Freshness in days (default: {DEFAULT_FRESHNESS_DAYS})",
    )

    args = parser.parse_args()
    jobs = scrape_naukri(
        keyword=args.keyword,
        max_pages=args.pages,
        freshness_days=args.freshness,
        output_dir=args.output,
    )

    print(f"\nDone! Scraped {len(jobs)} job(s) for '{args.keyword}'")
