# Concerns & Risks

## Security

| Concern | Impact | Likelihood | Mitigation |
|---------|--------|-----------|------------|
| API keys in plaintext `.env` | Key theft → billing abuse | Medium | `.gitignore`, file permission check |
| Gmail App Password in `.env` | Email account compromise | Medium | App Passwords are revocable |
| No input sanitization | Low (no SQL/shell exec) | Low | Acceptable for batch processing |
| No rate limiting on scraping | IP block from Naukri/Akamai | High | Add random delays + jitter |

## Stability

| Concern | Impact | Likelihood | Mitigation |
|---------|--------|-----------|------------|
| Naukri DOM class names change | Scraper returns 0 jobs | Medium | Monitor after Naukri frontend updates |
| Selenium browser crash mid-run | Jobs lost for remaining keywords | Medium | `try/finally` ensures cleanup |
| OpenRouter API downtime | Fallback keywords (lower quality) | Low | Retry with backoff |
| Chrome memory leak (~500 MB) | OOM on low-RAM servers | Medium | Restart browser per keyword (already done) |
| CAPTCHA/interstitial on Naukri | Scraper blocked entirely | Low | Manual intervention required |

## Scalability

| Concern | Impact | Likelihood | Mitigation |
|---------|--------|-----------|------------|
| Single-threaded processing | Linear scaling with candidates | Certain | Acceptable for <50 candidates |
| Filesystem storage limits | Disk full on large datasets | Low | Currently <100 MB total |
| Gmail 500/day email limit | Pipeline blocks on email | Low (small user base) | Switch to SendGrid at scale |
| No concurrent browser sessions | Can't parallelize scraping | Medium | Future: async with browser pool |

## Maintainability

| Concern | Impact | Likelihood | Mitigation |
|---------|--------|-----------|------------|
| Column name hardcoding | Pipeline breaks if form changes | High | Use substring matching (`_g()`) |
| No formal test suite | Regression risk on changes | High | Add unit tests for core logic |
| Hardcoded constants | Config changes require code edits | Medium | Move to `.env` or config file |
| No CI/CD pipeline | Manual deploy, no test gate | High | Add GitHub Actions workflow |
| Python version dependency | v3.11 features used | Low | Document minimum Python version |

## Reliability

| Concern | Impact | Likelihood | Mitigation |
|---------|--------|-----------|------------|
| SMTP failure → email lost | Candidates miss job report | Medium | Logged; manual re-send via `resend_emails.py` |
| LLM scoring inconsistency | Same job scored differently each run | High | Consider deterministic scoring fallback |
| Sent history file corruption | Duplicate emails sent | Low | File is append-only, corruption unlikely |
| No pipeline health check | Silent failure until next run | Medium | Add email/Slack alert on failure |

## Technical Debt

| Item | Description | Effort to Fix |
|------|-------------|--------------|
| `_g()` substring matching | Fragile column name matching | Low → switch to exact column config |
| Matched file list in `resend_emails.py` | Hardcoded file paths | Low → auto-detect latest matched files |
| No config file for search parameters | Pages, freshness, model hardcoded | Low → JSON/YAML config |
| No parallel scraping | Sequential per-keyword scraping | Medium → ThreadPoolExecutor |
