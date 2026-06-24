# Architecture

## System Overview

JobPilot is a **batch-processing pipeline** with no real-time components, no API, and no database. It runs on a schedule, processes all candidates sequentially, and outputs results to the filesystem and email.

## Layer Diagram

```
┌──────────────────────────────────────────────────┐
│               Scheduler (Orchestrator)             │
│           scripts/run_scheduler.py                 │
├──────────────────────────────────────────────────┤
│                                                     │
│   ┌──────────────┐   ┌──────────────────────┐      │
│   │  Phase 1-2    │   │     Phase 3          │      │
│   │  Data Intake  │   │  Job Search Agent    │      │
│   │  + Resume     │──▶│                      │      │
│   │  Parsing      │   │  keyword_gen → scrape│      │
│   │               │   │  → filter → score    │      │
│   │  pipeline.py  │   │  → email              │      │
│   └──────────────┘   └──────────────────────┘      │
│                                                     │
└──────────────────────────────────────────────────┘
```

## Component Relationships

### Phase 1: Intake
```
fetch_intake.py → fetcher.py → pandas.read_csv → Google Sheet CSV
                                   ↓
                              data/backups/intake_*.csv
```

### Phase 2: Resume Parsing
```
pipeline.py → downloader.py (Drive) → extractor.py (PDF/DOCX) → analyzer.py
                ↓                                                        ↓
           data/resumes/                                         data/profiles/profile_*.json
```

### Phase 3: Job Search
```
search_agent.py → keyword_gen.py → LLM → keywords
                    ↓
              naukri_scraper.py → Selenium → Naukri.com → jobs
                    ↓
              experience_filter.py → hard-filter → filtered jobs
                    ↓
              job_matcher.py → LLM → scored jobs
                    ↓
              email_sender.py → SMTP → candidate inbox
                    ↓
              sent_history.py → data/sent_history/*.json
```

## Data Flow

```
Google Form → CSV export → DataFrame → CandidateProfile → combine() → flat dict
                                                                          ↓
                                                 keyword_gen → scrape → filter → score → email
```

## Design Patterns

| Pattern | Usage |
|---------|-------|
| **Pipeline** | Sequential stages: fetch → parse → search → score → email |
| **Strategy** | Configurable LLM model, page count, freshness days |
| **Template Method** | Scrape flow consistent across keywords |
| **Fallback Chain** | LLM → hardcoded keywords; LLM → empty scoring |
| **Dataclass + combine()** | Form data + parsed resume merged into flat dict |

## Key Design Decisions

1. **Flat files over database**: Simpler deployment, sufficient for batch data volume
2. **Sequential processing**: Avoids browser conflicts from parallel Selenium instances
3. **Experience pre-filter before LLM**: Reduces API costs by 30-50%
4. **Visible Chrome**: Required by Naukri's Akamai CDN
5. **Sent-history files per candidate**: Enables accurate dedup across pipeline runs
