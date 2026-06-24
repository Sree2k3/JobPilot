# JobPilot

Automated job-matching system that ingests candidate profiles via Google Forms, parses resumes, scrapes matching job opportunities, and emails ranked reports to candidates.

---

## Version 1 (✅ Complete)

**V1** is a flat-file pipeline: Google Form → Sheet CSV → local JSON profiles → Naukri scraping → LLM scoring → email delivery.

### Project Structure

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
│   ├── search_jobs.py    # Phase 3: LLM-powered job search agent entry-point
│   ├── run_scheduler.py  # 24/7 scheduler (Mon/Thu 9 AM)
│   ├── generate_pdf.py   # PDF generator for design docs
│   └── resend_emails.py  # Re-send without re-scraping
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
│       │   ├── email_sender.py     # Email delivery with CSV attachment
│       │   └── sent_history.py     # Dedup tracker for sent jobs
│       └── utils/
│           ├── __init__.py
│           └── ...
│
├── data/
│   ├── backups/          # CSV backups of intake data (git-ignored)
│   ├── resumes/          # Downloaded resume PDFs (git-ignored)
│   ├── profiles/         # Candidate profile JSONs (git-ignored)
│   ├── scraped/          # Scraped job listings CSV/JSON (git-ignored)
│   └── sent_history/     # Tracks which jobs were sent to whom (git-ignored)
│
├── logs/                 # Run logs (git-ignored)
│
├── pdfs/                 # Design documents & generated PDFs
├── artifacts/            # Architecture diagrams & screenshots
├── tests/
│   ├── __init__.py
│   ├── test_intake.py
│   └── test_dedup.py
└── .planning/            # GSD planning directory
```

### V1 Phase Progress

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | User Intake Pipeline (Form → Sheet → Fetcher) | ✅ Complete |
| 2 | Resume Parsing Agent (Download → Extract → Analyze → Profile) | ✅ Complete |
| 3 | Scraper Agents (Keyword Gen → Naukri Scrape → Experience Filter → LLM Score → Email) | ✅ Complete |

### V1 Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env

# Phase 1: Fetch form responses
python scripts/fetch_intake.py

# Phase 2: Download and parse resumes
python scripts/parse_resumes.py

# Phase 2 with LLM enhancement (requires OPENAI_API_KEY)
python scripts/parse_resumes.py --llm

# Phase 3: Scrape jobs from Naukri.com (opens a visible Chrome window)
python scripts/scrape_jobs.py "python developer" --pages 3

# Phase 3: LLM-powered job search for a specific candidate (scrape + score + email)
python scripts/search_jobs.py --name "Sunil" --pages 3

# Run the full scheduler (24/7 daemon)
python scripts/run_scheduler.py

# Run the full scheduler once (for testing)
python scripts/run_scheduler.py --once

# Run the scheduler for one candidate (scrape + score + email)
python scripts/run_scheduler.py --name "Rajesh"
```

---

## Version 2 — Roadmap (🚧 Planned)

V2 transforms the flat-file prototype into a **database-backed, multi-threaded pipeline** with proper state management, monitoring, and failure recovery.

### Core Goals

1. **Replace flat files with a SQLite database** — single source of truth for all pipeline data
2. **Multi-threaded execution** — up to 4 candidates processed simultaneously
3. **State machine architecture** — each candidate pipeline has explicit states (idle → queued → scraping → scoring → emailing → done)
4. **Monitoring & audit** — view candidate status, run logs, and sent history in real-time

---

### 1. Database Layer (SQLite)

A single `jobpilot.db` file with the following tables:

#### `candidates`
Stores all candidate data (migrated from CSV → JSON profiles).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `full_name` | TEXT | |
| `email` | TEXT | |
| `phone` | TEXT | |
| `current_city` | TEXT | |
| `current_job_title` | TEXT | |
| `total_experience_years` | TEXT | "25-30 Years", "Fresher", etc. |
| `current_company` | TEXT | |
| `notice_period` | TEXT | |
| `preferred_locations` | TEXT | |
| `preferred_roles` | TEXT | |
| `employment_type` | TEXT | |
| `work_mode` | TEXT | |
| `seniority_level` | TEXT | |
| `department` | TEXT | |
| `resume_drive_link` | TEXT | |
| `skills` | TEXT | JSON array of skills |
| `technical_skills` | TEXT | JSON array |
| `work_experiences` | TEXT | JSON array |
| `education` | TEXT | JSON array |
| `certifications` | TEXT | JSON array |
| `professional_summary` | TEXT | |
| `consents` | TEXT | JSON object |
| `created_at` | DATETIME | Row creation timestamp |
| `updated_at` | DATETIME | Last updated |

#### `candidate_flags`
Controls whether a candidate is eligible for automated scheduling.

| Column | Type | Description |
|--------|------|-------------|
| `candidate_id` | INTEGER PK | FK → candidates.id |
| `scheduling_flag` | INTEGER | **0** = schedule this candidate, **1** = skip scheduling |
| `reason` | TEXT | Why the flag was set (e.g., "on_hold", "unsubscribed", "blacklisted") |
| `set_by` | TEXT | "system" or "admin" |
| `set_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Last modified |

**Flag logic:**
- `scheduling_flag = 0` → Candidate will be picked up in the next scheduler run
- `scheduling_flag = 1` → Candidate is skipped during automated runs (manual override)

#### `sent_jobs`
Tracks which job listings were sent to which candidate and when. Replaces the current flat-file `data/sent_history/`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `candidate_id` | INTEGER | FK → candidates.id |
| `job_title` | TEXT | |
| `company` | TEXT | |
| `application_link` | TEXT | Unique job identifier |
| `match_score` | INTEGER | 0–100 |
| `recommendation` | TEXT | "strong" / "moderate" / "weak" |
| `sent_at` | DATETIME | When the email was dispatched |
| `email_batch_id` | INTEGER | Groups jobs sent in one email |

#### `email_log`
Monitors every email sent by the system for audit.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `candidate_id` | INTEGER | FK → candidates.id |
| `recipient_email` | TEXT | |
| `subject` | TEXT | Email subject line |
| `job_count` | INTEGER | Number of jobs in this email |
| `status` | TEXT | "sent" / "failed" / "deferred" |
| `error_message` | TEXT | SMTP error if failed |
| `sent_at` | DATETIME | |
| `email_type` | TEXT | "job_report" or "no_jobs_notification" |

#### `pipeline_log`
Structured log of every pipeline run (replaces `logs/scheduler.json`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `run_start` | DATETIME | |
| `run_end` | DATETIME | |
| `trigger` | TEXT | "scheduled" / "manual" / "cli" |
| `candidates_processed` | INTEGER | |
| `total_jobs_found` | INTEGER | |
| `strong_matches` | INTEGER | |
| `emails_sent` | INTEGER | |
| `errors` | TEXT | JSON array of error messages |
| `success` | BOOLEAN | |

#### `search_cache`
Caches scraped + scored results per candidate so the same data can be re-emailed without re-scraping.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `candidate_id` | INTEGER | FK → candidates.id |
| `keywords` | TEXT | JSON array of keywords used |
| `jobs` | TEXT | JSON array of scored job objects |
| `created_at` | DATETIME | |

---

### 2. Multi-Threading Architecture

Replace the current sequential `for candidate in candidates` loop with a **thread-pool executor**:

```
                    ┌──────────────┐
                    │  Dispatcher  │
                    │  (main loop) │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Thread Pool │  (configurable, default 4)
                    │  max_workers │
                    └──────┬───────┘
                           │
                ┌──────────┼──────────┬──────────┐
                ▼          ▼          ▼          ▼
          ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
          │Worker 1 │ │Worker 2 │ │Worker 3 │ │Worker 4 │
          │Sunil    │ │Rajesh   │ │Sreedhar │ │Sachin   │
          └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
               │           │           │           │
          ─────┴───────────┴───────────┴───────────┴── time
```

Each worker is fully independent — it has its own Chrome/Selenium session, its own LLM API calls, and its own DB writes. No shared state between workers except the DB connection (via connection pooling).

**Key design choices:**
- `concurrent.futures.ThreadPoolExecutor` for CPU-bound I/O (network calls, scraping, LLM)
- Thread-local DB sessions via SQLAlchemy or raw `sqlite3` with thread-safe WAL mode
- Graceful shutdown: SIGINT drains the in-progress workers before exiting
- Per-worker timeout: if a candidate's pipeline hangs (>15 min), it's killed and retried

---

### 3. State Machine

Every candidate pipeline moves through a deterministic state machine:

```
                     ┌───────────┐
                     │   IDLE    │ ◄──── Start / Reset
                     └─────┬─────┘
                           │
                     ┌─────▼─────┐
                     │  QUEUED   │ ◄──── Dispatcher picks up
                     └─────┬─────┘
                           │
                    ┌──────▼──────┐
                    │ GENERATING  │ ◄──── LLM keyword generation
                    │  KEYWORDS   │
                    └──────┬──────┘
                           │
                     ┌─────▼─────┐
                     │ SCRAPING  │ ◄──── Naukri.com (Selenium)
                     └─────┬─────┘
                           │
                   ┌───────▼───────┐
                   │  FILTERING    │ ◄──── Experience pre-filter
                   └───────┬───────┘
                           │
                     ┌─────▼─────┐
                     │  SCORING  │ ◄──── LLM job matching
                     └─────┬─────┘
                           │
                     ┌─────▼─────┐
                     │  SAVING   │ ◄──── Write results to DB
                     └─────┬─────┘
                           │
                     ┌─────▼─────┐
                     │  EMAILING │ ◄──── Send report / no-jobs notification
                     └─────┬─────┘
                           │
                      ┌────▼────┐
                      │  DONE   │
                      └─────────┘

Error / Timeout ────► ┌───────────┐
                       │  FAILED   │ ◄──── Can be retried (→ QUEUED)
                       └───────────┘
```

**State transitions tracked in DB (`pipeline_log`):**
- Every state change records `candidate_id`, `from_state`, `to_state`, `timestamp`, and `metadata` (e.g., error message)
- A dashboard query can show "Rajesh is currently SCRAPING (started 30s ago)"

---

### 4. Migration Strategy (V1 → V2)

| Step | Action |
|------|--------|
| 1 | Create `jobpilot.db` with all table schemas |
| 2 | Write migration script to read `data/profiles/*.json` + `data/sent_history/*.json` → populate DB |
| 3 | Replace `config/settings.py` file-path config with DB config |
| 4 | Rewrite `search_agent.py` to read/write from DB instead of files |
| 5 | Implement `candidate_flags` table — default all V1 candidates to `scheduling_flag = 0` |
| 6 | Implement thread-pool dispatcher in `run_scheduler.py` |
| 7 | Implement state machine with DB-persisted transitions |
| 8 | Add monitoring queries (`python -m jobpilot.monitor` for CLI dashboard) |
| 9 | Remove old flat-file I/O (profiles/, scraped/, sent_history/) after migration verified |

---

### 5. CLI Monitoring (Post-Migration)

```bash
# Show all candidates and their current state
python -m jobpilot.monitor status

# Show today's pipeline run summary
python -m jobpilot.monitor today

# Show what was sent to a specific candidate
python -m jobpilot.monitor history --name "Rajesh"

# Enable/disable scheduling for a candidate
python -m jobpilot.monitor flag --name "Sunil" --value 0

# Re-run a failed candidate pipeline
python -m jobpilot.monitor retry --name "Sreedhar"
```

---

### 6. Dependencies to Add (V2)

```
# requirements.txt additions for V2
sqlalchemy>=2.0          # ORM / DB interaction
alembic>=1.13            # DB migrations
```

---

## V1 Implementation History

See [`implementation_log.md`](implementation_log.md) for the full V1 build log.
