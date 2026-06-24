# Testing

## Current Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_intake.py` | Intake fetching logic | ✅ Present |
| `tests/test_dedup.py` | Sent-history dedup functions | ✅ Present |

## What Is NOT Tested

| Module | Risk Level | Notes |
|--------|-----------|-------|
| `naukri_scraper.py` | 🔴 High | Requires live Chrome + Naukri.com — integration test only |
| `experience_filter.py` | 🔴 High | Complex matching logic — should be unit-tested |
| `email_sender.py` | 🟡 Medium | HTML rendering, CSV attachment, header generation |
| `job_matcher.py` | 🟡 Medium | LLM response parsing, fallback behavior |
| `keyword_gen.py` | 🟡 Medium | LLM response parsing, fallback chain |
| `search_agent.py` | 🟡 Medium | Orchestration logic, fresher detection |
| `llm_client.py` | 🟡 Medium | Retry logic, JSON extraction, timeout handling |
| `models.py` | 🟢 Low | Dataclass construction, `combine()` logic |
| `pipeline.py` | 🟡 Medium | Profile building, dedup, consent checks |
| `run_scheduler.py` | 🟡 Medium | Calendar logic, trigger detection, run logging |

## Test Pyramid (Desired)

```
    /\          E2E: Full pipeline with mock data (1-2)
   /  \         Integration: LLM client, scraper (3-5)
  /    \        Unit: Models, experience filter, dedup (10-15)
```

## Testing Recommendations

### Priority 1: Unit Tests
```python
# experience_filter.py
test_parse_candidate_experience_fresher()
test_parse_candidate_experience_range()
test_is_experience_match_within_tolerance()
test_prefilter_by_experience_keeps_good_jobs()

# sent_history.py
test_filter_new_jobs_all_new()
test_filter_new_jobs_some_duplicates()
test_mark_as_sent_appends_correctly()
```

### Priority 2: Integration Tests
```python
# llm_client.py
test_call_llm_json_returns_valid()
test_call_llm_json_retries_on_failure()
test_call_llm_json_strips_code_fences()

# email_sender.py
test_build_html_body_valid_html()
test_build_csv_bytes_has_all_fields()
test_is_email_configured_checks_env()
```

## Known Gaps
- No CI pipeline configured
- No test fixtures (sample profile JSONs, resumes)
- Manual testing required for Naukri scraper
- No coverage measurement tool configured
