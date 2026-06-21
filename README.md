# JobPilot

Automated job-matching system that ingests candidate profiles via Google Forms, parses resumes, and scrapes matching job opportunities.

## Project Structure

```
Joblist/
├── .env                  # Environment variables (git-ignored)
├── .env.example          # Environment template
├── .gitignore
├── README.md
├── implementation_log.md # Progress tracking
│
├── config/
│   ├── __init__.py
│   └── settings.py       # Environment-based configuration
│
├── requirements.txt      # All project dependencies (pip install -r)
├── scripts/
│   ├── fetch_intake.py   # Phase 1: CSV fetcher entry-point
│   ├── parse_resumes.py  # Phase 2: Resume parsing pipeline
│   ├── scrape_jobs.py    # Phase 3: Naukri.com job scraper entry-point
│   └── search_jobs.py    # Phase 3: LLM-powered job search agent entry-point
│
├── src/
│   └── jobpilot/
│       ├── __init__.py
│       ├── intake/       # Phase 1: Intake pipeline (form → sheet → fetch)
│       │   ├── __init__.py
│       │   └── fetcher.py
│       ├── parser/       # Phase 2: Resume parsing agent
│       │   ├── __init__.py
│       │   ├── models.py      # Data models (ParsedResume, CandidateProfile)
│       │   ├── downloader.py  # Google Drive file downloader
│       │   ├── extractor.py   # PDF/DOCX text extraction
│       │   ├── analyzer.py    # Resume analysis (local + optional LLM)
│       │   └── pipeline.py    # End-to-end pipeline orchestrator (+ dedup)
│       ├── scraper/      # Phase 3: Job scraper agents
│       │   ├── __init__.py
│       │   ├── naukri_scraper.py   # Naukri.com scraper (Selenium)
│       │   ├── llm_client.py       # OpenRouter LLM wrapper
│       │   ├── keyword_gen.py      # LLM keyword generator agent
│       │   ├── job_matcher.py      # LLM job scoring agent
│       │   ├── search_agent.py     # Orchestrator: keyword→scrape→score→email
│       │   ├── experience_filter.py # Hard experience pre-filter
│       │   └── email_sender.py     # Email delivery with CSV attachment
│       └── utils/        # Shared utilities
│           ├── __init__.py
│           └── ...       # (to be implemented)
│
├── data/
│   ├── backups/          # CSV backups of intake data (git-ignored)
│   ├── resumes/          # Downloaded resume PDFs (git-ignored)
│   ├── profiles/         # Candidate profile JSONs (git-ignored)
│   └── scraped/          # Scraped job listings CSV/JSON (git-ignored)
│
├── logs/                 # Run logs (git-ignored)
│
└── tests/
    ├── __init__.py
    ├── test_intake.py
    └── test_dedup.py     # Dedup index loader tests
```

## Phase Progress

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | User Intake Pipeline (Form → Sheet → Fetcher) | ✅ Complete |
| 2 | Resume Parsing Agent (Download → Extract → Analyze) | ✅ Complete |
| 3 | Scraper Agents (Naukri.com + LLM Agent) | 🚧 In Progress | **~60%** |

## Quick Start

```bash
# Install ALL dependencies (Phase 1 + 2 + 3)
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env -> paste your published Sheet CSV URL
# Add OPENROUTER_API_KEY and SMTP_* for Phase 3

# Phase 1: Fetch form responses
python scripts/fetch_intake.py

# Phase 2: Download and parse resumes
python scripts/parse_resumes.py

# Phase 2 with LLM enhancement (requires OPENAI_API_KEY in .env)
python scripts/parse_resumes.py --llm

# Phase 3: Scrape jobs from Naukri.com (opens a visible Chrome window)
python scripts/scrape_jobs.py "python developer" --pages 3

# Phase 3: LLM-powered job search for a specific candidate (scrape + score + email)
python scripts/search_jobs.py --name "Sreekant" --pages 2
```
