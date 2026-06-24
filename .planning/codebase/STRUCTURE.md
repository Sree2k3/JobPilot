# Repository Structure

## File Tree

```
D:\Joblist/
├── .env                           # Secrets (SHEET_CSV_URL, API keys, SMTP)
├── .gitignore
├── README.md
├── requirements.txt               # Python dependencies
│
├── config/                        # Application configuration
│   ├── __init__.py
│   └── settings.py                # Loads .env, exposes get_settings() dict
│
├── scripts/                       # CLI entry points
│   ├── fetch_intake.py            # Phase 1 CLI
│   ├── parse_resumes.py           # Phase 2 CLI
│   ├── search_jobs.py             # Phase 3 CLI (--name, --pages, --freshness, --model)
│   ├── run_scheduler.py           # Full pipeline scheduler (daemon or --once)
│   ├── resend_emails.py           # Re-send from saved matched files
│   ├── scrape_jobs.py             # Direct scraper CLI
│   └── generate_pdf.py            # PDF documentation generator
│
├── src/jobpilot/
│   ├── __init__.py
│   │
│   ├── intake/                    # Data ingestion (Phase 1)
│   │   ├── __init__.py
│   │   └── fetcher.py             # fetch_all(), show_summary(), save_backup()
│   │
│   ├── parser/                    # Resume parsing (Phase 2)
│   │   ├── __init__.py
│   │   ├── models.py              # CandidateProfile, ParsedResume, WorkExperience, Education
│   │   ├── downloader.py          # download_all_resumes() from Google Drive
│   │   ├── extractor.py           # extract_text() from PDF/DOCX
│   │   ├── analyzer.py            # analyze_resume() text → structured data
│   │   └── pipeline.py           # run_pipeline() orchestrator
│   │
│   ├── scraper/                   # Job scraping & matching (Phase 3)
│   │   ├── __init__.py
│   │   ├── llm_client.py          # call_llm_json() — OpenRouter wrapper
│   │   ├── keyword_gen.py         # generate_keywords() — LLM → search terms
│   │   ├── naukri_scraper.py      # scrape_naukri() — Selenium Chrome scraper
│   │   ├── search_agent.py        # search_for_candidate() — full orchestration
│   │   ├── experience_filter.py   # prefilter_by_experience() — hard filter
│   │   ├── job_matcher.py         # score_jobs() — LLM scoring
│   │   ├── email_sender.py        # send_job_report() — SMTP delivery
│   │   └── sent_history.py        # filter_new_jobs(), mark_as_sent()
│   │
│   └── utils/
│       └── __init__.py
│
├── data/                          # Runtime data
│   ├── profiles/                  # profile_{Name}_{index}.json
│   ├── scraped/                   # naukri_*.csv/json, matched_*.csv/json
│   ├── resumes/                   # Downloaded PDF/DOCX
│   ├── sent_history/              # sent_{email}_{name}.json
│   └── backups/                   # intake_{timestamp}.csv
│
├── logs/
│   ├── scheduler.json             # Pipeline run history
│   └── calendar_cache.json        # Next scheduled run cache
│
├── tests/
│   ├── __init__.py
│   ├── test_intake.py             # Intake fetching tests
│   └── test_dedup.py              # Sent-history dedup tests
│
├── pdfs/                          # Generated documentation
│   ├── README.md
│   └── JobPilot_Design_Document.md/pdf
│
└── .planning/codebase/            # Codebase analysis (this directory)
    ├── STACK.md
    ├── INTEGRATIONS.md
    ├── ARCHITECTURE.md
    ├── STRUCTURE.md
    ├── CONVENTIONS.md
    ├── TESTING.md
    └── CONCERNS.md
```

## Module Dependency Graph

```
scripts/run_scheduler.py
  ├── src/jobpilot/parser/pipeline.py
  │     ├── fetcher.py
  │     ├── downloader.py
  │     ├── extractor.py
  │     ├── analyzer.py
  │     └── models.py
  └── src/jobpilot/scraper/search_agent.py
        ├── keyword_gen.py → llm_client.py
        ├── naukri_scraper.py
        ├── experience_filter.py
        ├── job_matcher.py → llm_client.py
        ├── email_sender.py
        └── sent_history.py

scripts/search_jobs.py
  └── search_agent.py (same tree as above)

config/settings.py
  └── All modules (via get_settings())
```

## Key Imports Flow

```
settings.py: os.getenv(), python-dotenv
fetcher.py: pandas, os
models.py: dataclasses, datetime
downloader.py: gdown, requests
extractor.py: pdfminer, docx
analyzer.py: re, json
naukri_scraper.py: selenium, csv, json, time
llm_client.py: openai, json
keyword_gen.py: llm_client
job_matcher.py: llm_client
email_sender.py: smtplib, email.mime, csv
sent_history.py: json, os, datetime
```
