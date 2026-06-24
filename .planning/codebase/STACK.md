# Technology Stack

## Runtime

| Technology | Version | Purpose | Why Chosen |
|-----------|---------|---------|------------|
| Python | 3.11+ | Primary runtime | Rich ecosystem for data processing, LLM integration, web scraping |
| python-dotenv | 1.x | Environment config | Standard .env loading, zero dependencies |

## Data Processing

| Technology | Version | Purpose |
|-----------|---------|---------|
| pandas | 2.x | CSV parsing from Google Sheets, DataFrame operations |
| pdfminer.six | — | PDF text extraction from resumes |
| python-docx | — | DOCX text extraction from resumes |
| gdown | — | Download files from Google Drive links |

## AI / LLM

| Technology | Purpose |
|-----------|---------|
| openai (SDK) | OpenRouter API client (compatible OpenAI SDK) |
| OpenRouter API | Gateway to multiple LLMs through single endpoint |
| deepseek/deepseek-chat | Default LLM for keyword gen + job scoring |

## Web Scraping

| Technology | Purpose |
|-----------|---------|
| Selenium 4.x | Browser automation for Naukri.com scraping |
| Chrome Browser | Required by Naukri's Akamai CDN (blocks headless) |

## Email

| Technology | Purpose |
|-----------|---------|
| smtplib (stdlib) | SMTP email delivery |
| email.mime (stdlib) | MIME multipart message construction |
| Gmail SMTP (smtp.gmail.com:587) | Email relay with App Password auth |

## PDF Generation (Documentation)

| Technology | Purpose |
|-----------|---------|
| fpdf2 | Generate PDF from markdown documentation |

## Alternatives Considered

| Rejected | Reason |
|----------|--------|
| Django / FastAPI | No HTTP API needed — pure batch processing |
| PostgreSQL / MongoDB | Overkill for batch pipeline; JSON files suffice |
| Scrapy | Naukri blocks bot user-agents; real browser required |
| Requests / httpx | Cannot bypass Akamai CDN |
| LangChain / CrewAI | Only 2 LLM calls per candidate — framework overhead unjustified |
| Docker | Not yet needed; can be containerized later |
| WeasyPrint / pdfkit | Not available on Windows without GTK/wkhtmltopdf |
