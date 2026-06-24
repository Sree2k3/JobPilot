"""
Indeed.com job scraper.

Uses Playwright with stealth settings to search in.indeed.com and extract
job listings. The scraper handles Indeed's anti-bot protections by:
  - Using Playwright headless mode (stealthier than Selenium)
  - Setting realistic user-agent and viewport
  - Limiting to page 1 per keyword (Indeed redirects page 2+ to login)
  - Cookie persistence across runs

Each scrape_keyword() call creates its OWN Playwright context (browser
is shared within one scrape_keyword call, but each thread gets its own),
making it thread-safe for use with ThreadPoolExecutor.

Selectors are based on Indeed's current DOM structure:
  - a.jobTitle        → job title + link (has "jk" param in href)
  - span.companyName  → company name
  - div.companyLocation → location text
  - span.salary-snippet → salary (when available)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from ..base import BaseJobScraper, CSV_HEADERS

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────────

INDEED_BASE = "https://in.indeed.com"
SEARCH_URL = "https://in.indeed.com/jobs"
DEFAULT_JOBS_PER_KEYWORD = 10

# Playwright timeouts (ms)
NAVIGATION_TIMEOUT = 30000
WAIT_TIMEOUT = 10000
SCROLL_WAIT_MS = 1500

COOKIE_DIR = Path("data") / "cookies"
COOKIE_FILE = COOKIE_DIR / "indeed_cookies.json"


# ── JS extractor ─────────────────────────────────────────────────────────

def _extract_script() -> str:
    """JavaScript that extracts all job cards from the current Indeed page."""
    return """
    () => {
        const cards = document.querySelectorAll('[data-testid="job-card"], .job_seen_beacon, .result');
        const titleLinks = document.querySelectorAll('a.jobTitle');
        const targets = cards.length >= titleLinks.length ? cards : titleLinks;
        const results = [];
        const seen = new Set();
        targets.forEach((card, idx) => {
            const titleEl = card.querySelector
                ? card.querySelector('a.jobTitle, .jobTitle, [data-jk]')
                : null;
            const titleLink = titleEl || (card.matches && card.matches('a.jobTitle') ? card : null);
            const title = titleLink
                ? (titleLink.innerText || titleLink.textContent || '').trim()
                : (card.innerText || card.textContent || '').trim().split('\\n')[0];
            const companyEl = card.querySelector
                ? card.querySelector('span.companyName, [data-testid="company-name"]')
                : null;
            const company = companyEl ? companyEl.innerText.trim() : '';
            const locEl = card.querySelector
                ? card.querySelector('div.companyLocation, [data-testid="text-location"]')
                : null;
            const location = locEl ? locEl.innerText.trim() : '';
            const salaryEl = card.querySelector
                ? card.querySelector('span.salary-snippet, [data-testid="attribute-text"]')
                : null;
            const salary = salaryEl ? salaryEl.innerText.trim() : '';
            let link = '';
            const anchor = titleLink || (card.querySelector ? card.querySelector('a') : null);
            if (anchor && anchor.href) {
                link = anchor.href;
                if (link.includes('/rc/clk')) {
                    const jkMatch = link.match(/jk=([a-f0-9]+)/);
                    if (jkMatch) link = 'https://in.indeed.com/viewjob?jk=' + jkMatch[1];
                }
            } else {
                const jk = card.getAttribute ? card.getAttribute('data-jk') : null;
                if (jk) link = 'https://in.indeed.com/viewjob?jk=' + jk;
            }
            const dedupKey = link || `${title}|${company}`;
            if (seen.has(dedupKey)) return;
            seen.add(dedupKey);
            results.push({ title, company, location, salary, link });
        });
        return results;
    }
    """


# ── Scraper class ────────────────────────────────────────────────────────

class IndeedScraper(BaseJobScraper):
    """
    Thread-safe Indeed.com scraper.

    Each call to scrape_keyword() creates its own Playwright browser
    and context, scrapes 1 page of results, then closes.  This makes
    it safe to call from multiple threads.

    Usage:
        scraper = IndeedScraper()
        jobs = scraper.scrape_keyword("python developer", location="Bangalore")
        jobs = scraper.scrape_all(["python", "java", "go"], max_workers=3, location="Bangalore")
    """

    SOURCE_NAME = "Indeed"

    def __init__(self, output_dir: Optional[str] = None):
        super().__init__(output_dir)

    # ── Core scrape (thread-safe) ────────────────────────────────────

    def scrape_keyword(self, keyword: str, **kwargs) -> list[dict]:
        """
        Scrape Indeed for ONE keyword.  Thread-safe.

        Each call creates its own Playwright browser, loads 1 page
        of search results, extracts ~10 jobs, then closes.

        Args:
            keyword: Search term.
            **kwargs:
                location: Location filter (e.g. "Bangalore", "India").
                          Defaults to "India".

        Returns:
            List of job dicts matching CSV_HEADERS keys.
        """
        location = kwargs.get("location", "India")
        search_url = self._build_search_url(keyword, location)

        all_jobs: list[dict] = []
        p = None
        browser = None

        try:
            p = sync_playwright().start()
            browser, context = self._create_context(p)
            retry_without_cookies = False

            page = context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT)

            logger.info("[Indeed] Loading %s", search_url)
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
            except PlaywrightTimeout:
                logger.warning("[Indeed] Timeout loading search page")

            # Wait for page to settle — Indeed often shows an interstitial
            # (sign-in prompt, age verification, etc.) before job cards.
            page.wait_for_timeout(3000)

            # Check for sign-in / interstitial pages
            page_title = page.title().lower()
            current_url = page.url.lower()
            if "auth" in current_url or "sign" in page_title or "log in" in page_title:
                logger.warning("[Indeed] Redirected to auth page — marking cookies as stale")
                retry_without_cookies = True

            # Try scrolling down to trigger content load
            page.evaluate("window.scrollTo(0, 300)")
            page.wait_for_timeout(1000)

            # Wait for job cards
            cards_found = True
            try:
                page.wait_for_selector(
                    "a.jobTitle, .job_seen_beacon, [data-testid='job-card']",
                    timeout=WAIT_TIMEOUT,
                )
            except PlaywrightTimeout:
                logger.warning("[Indeed] Timeout waiting for job cards — page may have no results")
                cards_found = False

            page.wait_for_timeout(SCROLL_WAIT_MS)

            # Scroll for lazy content
            for _ in range(2):
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(500)

            # Extract jobs
            raw = page.evaluate(_extract_script())
            if raw and isinstance(raw, list):
                for j in raw:
                    all_jobs.append({
                        "source": "Indeed",
                        "job_title": (j.get("title") or "").strip(),
                        "company": (j.get("company") or "").strip(),
                        "experience_required": "",
                        "location": (j.get("location") or "").strip(),
                        "salary": (j.get("salary") or "").strip(),
                        "skills": [],
                        "application_link": (j.get("link") or "").strip(),
                    })
                logger.info("[Indeed] Extracted %d jobs from page", len(raw))
            else:
                logger.warning("[Indeed] No jobs extracted from page")

            page.close()

            # If we got redirected to auth, clear stale cookies so next run is fresh
            if retry_without_cookies or (not all_jobs and not cards_found):
                logger.info("[Indeed] Clearing stale cookies for next run")
                COOKIE_FILE.unlink(missing_ok=True)
            else:
                # Only save cookies if we got a valid result
                self._save_cookies(context)

        except Exception as e:
            logger.error("[Indeed] Unexpected error: %s", e)
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

        return all_jobs[:DEFAULT_JOBS_PER_KEYWORD]

    # ── Internals ──────────────────────────────────────────────────

    @staticmethod
    def _build_search_url(keyword: str, location: str) -> str:
        """Build the Indeed search URL for page 1."""
        params = f"?q={keyword.replace(' ', '+')}"
        if location:
            params += f"&l={location.replace(' ', '+')}"
        params += "&start=0"
        return f"{SEARCH_URL}{params}"

    @staticmethod
    def _create_context(playwright):
        """Create a Playwright browser + context with stealth settings."""
        browser = playwright.chromium.launch(
            headless=True,
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
        # Load saved cookies if available
        if COOKIE_FILE.exists():
            try:
                cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                logger.info("[Indeed] Loaded %d saved cookies", len(cookies))
            except Exception as e:
                logger.warning("[Indeed] Could not load cookies: %s", e)

        return browser, context

    @staticmethod
    def _save_cookies(context) -> None:
        """Persist browser cookies to disk."""
        try:
            cookies = context.cookies()
            COOKIE_DIR.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(
                json.dumps(cookies, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[Indeed] Could not save cookies: %s", e)


# ── Module-level convenience function (backwards-compatible) ─────────────

__all__ = [
    "IndeedScraper",
    "scrape_indeed",
]


def scrape_indeed(
    keyword: str,
    location: str = "India",
    output_dir: Optional[str] = None,
) -> list[dict]:
    """
    Convenience function: create an IndeedScraper, scrape one keyword,
    save results, return jobs.

    Preserves the original function signature for backwards compatibility.

    Args:
        keyword: Job search term.
        location: Location filter.
        output_dir: Output directory (default: data/scraped/).

    Returns:
        List of job dicts.
    """
    scraper = IndeedScraper(output_dir=output_dir)
    jobs = scraper.scrape_keyword(keyword, location=location)
    scraper.save_results(jobs, label=keyword)
    return jobs


# ── CLI entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Indeed.com job scraper")
    parser.add_argument("keyword", help="Job search keyword")
    parser.add_argument(
        "--location",
        default="India",
        help="Location filter (default: India)",
    )
    parser.add_argument("--output", default=None, help="Output directory")

    args = parser.parse_args()
    jobs = scrape_indeed(
        keyword=args.keyword,
        location=args.location,
        output_dir=args.output,
    )

    print(f"\nDone! Scraped {len(jobs)} job(s) from Indeed for '{args.keyword}'")
