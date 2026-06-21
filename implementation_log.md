# Implementation Progress Log

This file tracks the incremental implementation of the JobPilot system. Each entry records the date, component, status, and a brief note.

## Phase Plan

- **Phase 1 – User Intake Pipeline**: Create Google Form to collect target job role, desired position(s), years of experience, preferred location(s), employment type preferences, salary expectations, remote/hybrid/on-site preferences, additional preferences, and resume upload. Store responses automatically in a Google Sheet. Set up a cron scheduler to periodically monitor the sheet and fetch newly submitted records (reading only, no parsing).
- **Phase 2 – Resume Parsing Agent**: Build an agent that reads the uploaded resume, extracts structured information (skills, experience, education, preferred roles, location, keywords) and combines it with the user's form responses.
- **Phase 3 – Scraper Agents**: Use the structured profile data to drive scraper agents that search and collect matching job opportunities from various platforms.

## Implementation Log

### Phase 1 – User Intake Pipeline (✅ Complete)
- `2026-06-20`: Created package skeleton (`jobpilot/__init__.py`).
- `2026-06-20`: Added this log file and defined phase plan.
- `2026-06-20`: Created Google Form for candidate intake with 17 questions across 5 sections:
  - **Section 1 – Personal Information**: Full Name, Email Address, Phone Number, Current City/Location.
  - **Section 2 – Current Employment**: Current Job Title, Total Years of Experience (dropdown), Current Company, Notice Period (dropdown).
  - **Section 3 – Job Preferences**: Preferred Roles (checkbox + Other), Preferred Job Locations (checkbox), Employment Type, Work Mode Preference, Seniority Level.
  - **Section 4 – Consent**: Consent for Resume Parsing, Automated Job Search, and Email Delivery (3 checkboxes).
  - **Section 5 – Resume Upload**: File upload (PDF/DOCX, max 10 MB).
- `2026-06-20`: Linked Google Form to a Google Sheet for automatic response storage.
- `2026-06-20`: Published Google Sheet to web (CSV) for public read access (prototype phase).
- `2026-06-20`: Created `.env` and `.env.example` for environment variable management.
- `2026-06-20`: Added `.gitignore` to exclude `.env`, data files, and build artifacts.
- `2026-06-20`: Organized project into systematic folder structure.
- `2026-06-20`: Refactored intake logic into reusable module (`src/jobpilot/intake/fetcher.py`) with dedup-ready row hashing.
- `2026-06-20`: Created entry-point script (`scripts/fetch_intake.py`) with clean import path.
- `2026-06-20`: Added basic unit tests for row-hashing consistency in `tests/test_intake.py`.
- `2026-06-20`: Created `README.md` with project overview, structure map, and quick-start guide.
- `2026-06-20`: Removed old root-level `jobpilot/` package in favor of `src/jobpilot/` layout.
- `2026-06-20`: Configured `.env` with live published Sheet CSV URL and verified connectivity.

### Phase 2 – Resume Parsing Agent (✅ Complete)
- `2026-06-20`: Created data models (`src/jobpilot/parser/models.py`) — `WorkExperience`, `Education`, `ParsedResume`, `CandidateProfile` dataclasses with `combine()` for merging form + resume data.
- `2026-06-20`: Built Drive downloader (`src/jobpilot/parser/downloader.py`) — extracts file IDs from Google Drive URL formats and downloads via `gdown` with automatic file-type detection from magic bytes (PDF/DOCX).
- `2026-06-20`: Built text extractor (`src/jobpilot/parser/extractor.py`) — extracts text from PDFs (pdfplumber + PyPDF2 fallback) and DOCX files (python-docx). Supports no-extension files via magic byte sniffing.
- `2026-06-20`: Built local resume analyzer (`src/jobpilot/parser/analyzer.py`) — regex-based extraction of name, email, phone, location, LinkedIn/GitHub URLs, skills (with tech-skill classification), work experience, education, certifications, and languages. Includes optional LLM-enhanced extraction via OpenAI (gpt-4o-mini) when `OPENAI_API_KEY` is set.
- `2026-06-20`: Built pipeline orchestrator (`src/jobpilot/parser/pipeline.py`) — end-to-end flow: fetch sheet → download resumes → extract text → analyze → build CandidateProfile → save JSON profiles to `data/profiles/`.
- `2026-06-20`: Created entry-point (`scripts/parse_resumes.py`) with `--llm` flag for OpenAI enhancement.
- `2026-06-20`: **Successful end-to-end test** — submitted Google Form with resume (Sreekant Patnaik), pipeline downloaded PDF, extracted 40 skills, 1 work experience, 1 education entry; profile saved as `data/profiles/profile_Sreekant_Patnaik_0.json`.
- `2026-06-20`: Fixed `config/settings.py` PROJECT_ROOT path (was off by one directory).
- `2026-06-20`: Fixed emoji/Unicode display crashes on Windows cp1252 terminal.
- `2026-06-20`: Fixed column matching to distinguish "Resume Upload" from "Consent for Resume Parsing".
- `2026-06-20`: Fixed consent detection to handle full-sentence consent values ("I consent to...").
- `2026-06-20`: Fixed downloader to auto-detect and append correct file extension (.pdf/.docx).

### Phase 3 – Scraper Agents (🚧 In Progress)
- `2026-06-21`: Implemented dedup protection in `src/jobpilot/parser/pipeline.py`:
  - `_load_existing_profile_index()` scans `data/profiles/` on startup, builds email -> filename map
  - Skips re-processing any candidate whose email already exists (disk or same-batch)
  - Added `run_pipeline(dedup_check=True/False)` toggle
  - 7 tests in `tests/test_dedup.py`
- `2026-06-21`: Built Naukri.com job scraper (`src/jobpilot/scraper/naukri_scraper.py`):
  - Selenium-based crawler with stealth patches to bypass Akamai bot protection
  - Extracts: job title, company, experience, location, salary, skills, application link
  - Supports pagination across multiple result pages (20 jobs/page)
  - Saves output as CSV + JSON to `data/scraped/`
  - Entry point: `scripts/scrape_jobs.py <keyword> --pages N`
- `2026-06-21`: Created `requirements.txt` with all project dependencies.
- `2026-06-21`: Built **LLM-Powered Job Search Agent**:
  - `src/jobpilot/scraper/llm_client.py` — OpenRouter wrapper with JSON output parsing (supports any model)
  - `src/jobpilot/scraper/keyword_gen.py` — LLM agent that derives 3 optimal Naukri search keywords from a candidate profile
  - `src/jobpilot/scraper/job_matcher.py` — LLM agent that scores scraped jobs against a profile (0-100%, with skill_match, experience_fit, location_match, recommendation)
  - `src/jobpilot/scraper/search_agent.py` — Orchestrator: keyword gen → scrape → score → save ranked CSV+JSON
  - `scripts/search_jobs.py` — Entry point: `python scripts/search_jobs.py --name "Sreekant" --pages 3`
  - Verified: Sreekant's profile → keywords ["ai developer", "machine learning engineer", "python tensorflow developer"] → 14 jobs scored, **85-90%** top match (Generative AI Engineers @ Zensar)
- `2026-06-21`: Added email delivery module (`src/jobpilot/scraper/email_sender.py`):
  - Builds a clean HTML email with greeting and CSV attachment (no inline job table)
  - Attaches CSV with all details: job title, company, experience, location, salary, skills, missing skills, match score, application link
  - Uses SMTP (Gmail App Password) -- config via SMTP_* env vars
  - Integrated into search_agent.py: automatically emails candidate after search completes
  - Updated `scripts/search_jobs.py` to read candidate email from profile and pass it through
  - Added SMTP config vars to `.env.example`
- `2026-06-21`: Added strict experience pre-filter (`src/jobpilot/scraper/experience_filter.py`):
  - Parses candidate experience from profile ("Fresher" -> 0-1 yrs, numeric ranges, work history, education)
  - Parses job experience from Naukri listings ("0-2 Yrs", "Fresher", "2-5 Yrs", etc.)
  - Fresher (0-1): only jobs where min_experience == 0 (strictly fresher/internship roles)
  - Integrated into search_agent.py as Step 3a before LLM scoring
- `2026-06-21`: Added internship search for freshers in search_agent.py:
  - When candidate is a fresher, automatically appends "{keyword} internship" and "internship" keywords
  - Expanded to 6 keywords max, finds both full-time entry-level and internship listings
  - Tested: 109 jobs scraped -> 32 after filter -> 28 scored, 19 internship + 9 entry-level
- `2026-06-21`: Added missing skills column in search_agent.py and email CSV:
  - Compares each job's skills against candidate's full skill set (skills + technical_skills + experience descriptions)
  - Handles abbreviations (ML -> Machine Learning, NLP -> Natural Language Processing, etc.)
  - New "Missing Skills" column in CSV output for skill gap awareness
- `2026-06-21`: Enhanced multi-role keyword generation in keyword_gen.py:
  - LLM prompt expanded to handle comma-separated preferred roles ("Ai developer, Python developer")
  - Generates at least one search keyword per preferred role, outputs 3-6 keywords

---

## Completion Summary (as of 2026-06-21)

| Phase | Description | Status | % Complete |
|-------|-------------|--------|-----------|
| 1 | User Intake Pipeline (Form → Sheet → Fetcher) | ✅ Complete | 100% |
| 2 | Resume Parsing Agent (Download → Extract → Analyze → Profile) | ✅ Complete | 100% |
| 3 | Scraper Agents (Search job platforms using profile data) | 🚧 In Progress | ~60% |
| **Overall** | | | **~87%** |

### What's been built:
| Component | Files |
|-----------|-------|
| Google Form + Sheet integration | Form with 17 questions across 5 sections, CSV published |
| Intake fetcher | `src/jobpilot/intake/fetcher.py`, `scripts/fetch_intake.py` |
| Config & env management | `config/settings.py`, `.env`, `.env.example`, `.gitignore` |
| Data models | `src/jobpilot/parser/models.py` -- `ParsedResume`, `CandidateProfile`, etc. |
| Resume downloader | `src/jobpilot/parser/downloader.py` -- Drive URL to file (PDF/DOCX) |
| Text extractor | `src/jobpilot/parser/extractor.py` -- pdfplumber + PyPDF2 + python-docx |
| Resume analyzer (local) | `src/jobpilot/parser/analyzer.py` -- regex-based parsing (no API key needed) |
| Resume analyzer (LLM) | `src/jobpilot/parser/analyzer.py` -- OpenAI integration (requires key) |
| Pipeline orchestrator | `src/jobpilot/parser/pipeline.py` -- end-to-end flow (+ email-based dedup) |
| Naukri job scraper | `src/jobpilot/scraper/naukri_scraper.py` -- Selenium-based with stealth mode |
| LLM Client | `src/jobpilot/scraper/llm_client.py` -- OpenRouter wrapper with JSON parsing |
| Keyword Generator | `src/jobpilot/scraper/keyword_gen.py` -- LLM derives search keywords from profile |
| Job Matcher | `src/jobpilot/scraper/job_matcher.py` -- LLM scores jobs 0-100% against profile |
| Experience Pre-Filter | `src/jobpilot/scraper/experience_filter.py` -- Hard experience gating before LLM |
| Search Orchestrator | `src/jobpilot/scraper/search_agent.py` -- keyword -> scrape -> filter -> score -> save -> email |
| Email Sender | `src/jobpilot/scraper/email_sender.py` -- SMTP email with CSV attachment |
| Entry-point scripts | `scripts/fetch_intake.py`, `scripts/parse_resumes.py`, `scripts/scrape_jobs.py`, `scripts/search_jobs.py` |
| Dependencies | `requirements.txt` -- single pip install file |
| Tests | `tests/test_intake.py`, `tests/test_dedup.py` |
