# External Integrations

## 1. Google Sheets CSV

| Property | Value |
|----------|-------|
| **Purpose** | Read candidate form responses |
| **Method** | Published CSV URL (`pandas.read_csv`) |
| **Auth** | None (publicly published CSV) |
| **Error handling** | Hard fail — pipeline stops if sheet unreachable |
| **Frequency** | Every pipeline run |
| **Rate limits** | None (Google's CSV export is cached) |

## 2. Google Drive (Resume Downloads)

| Property | Value |
|----------|-------|
| **Purpose** | Download candidate resume files |
| **Method** | `gdown` library |
| **Auth** | None (publicly shared Drive links) |
| **Error handling** | Logged, skips to next candidate |
| **Failure modes** | HTTP 403 (link expired), HTTP 404 (file deleted) |

## 3. Naukri.com (Web Scraping)

| Property | Value |
|----------|-------|
| **Purpose** | Scrape job listings by keyword |
| **Method** | Selenium Chrome (visible browser, not headless) |
| **Auth** | None (public listings) |
| **URL pattern** | `https://www.naukri.com/{keyword}-jobs?freshness=N` |
| **Error handling** | Timeout → warning + continue; crash → next keyword |
| **Rate limiting** | None (static delays only — risk of Akamai blocks) |

### Anti-Detection Measures
- Visible browser (headless blocked by Akamai)
- Stealth patches: remove `navigator.webdriver`, set realistic user-agent/languages
- Home page warm-up for cookie/Akamai clearance
- Scroll simulation for lazy-loaded content

## 4. OpenRouter API (LLM)

| Property | Value |
|----------|-------|
| **Purpose** | Keyword generation + job scoring |
| **Method** | OpenAI SDK with custom base URL |
| **Auth** | API key (`OPENROUTER_API_KEY`) |
| **Default model** | `deepseek/deepseek-chat` |
| **Timeout** | 120 seconds per call |
| **Retry** | 3 attempts with exponential backoff |
| **Error handling** | Silent degradation (fallback keywords, empty scoring) |

### Request Flow
```
LLM Client → POST /api/v1/chat/completions → OpenRouter → DeepSeek API → Response
```

## 5. Gmail SMTP (Email)

| Property | Value |
|----------|-------|
| **Purpose** | Send HTML+CSV job reports |
| **Method** | `smtplib.SMTP` over TLS |
| **Server** | `smtp.gmail.com:587` |
| **Auth** | Gmail App Password (not primary password) |
| **Error handling** | Logged, pipeline continues |
| **Limits** | 500 emails/day for Gmail accounts |

## Integration Failure Summary

| Integration | Failure Mode | Impact | Mitigation |
|-------------|-------------|--------|------------|
| Google Sheets | Network error | Pipeline stops | none (critical) |
| Google Drive | 403/404 | Candidate skipped | Continue to next candidate |
| Naukri | Akamai block / timeout | Jobs lost for candidate | Retry on next run |
| OpenRouter | API down | Fallback keywords used | Reduced match quality |
| Gmail SMTP | Auth failure | Email not sent | Results saved to disk |
