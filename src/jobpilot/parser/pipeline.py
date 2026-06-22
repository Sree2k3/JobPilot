"""Full pipeline: fetch sheet -> download resumes -> extract text -> analyze -> build profiles."""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from .downloader import download_all_resumes, pdna
from .extractor import extract_text
from .analyzer import analyze_resume, analyze_with_llm
from .models import CandidateProfile, ParsedResume


def run_pipeline(
    use_llm: bool = False,
    llm_model: str = "gpt-4o-mini",
    output_dir: Optional[str] = None,
    dedup_check: bool = True,
) -> list[CandidateProfile]:
    """
    Run the full Phase 2 pipeline:

    1. Fetch responses from the Google Sheet
    2. Download resume files from Drive links
    3. Extract text from each resume
    4. Analyze resume text (local or LLM)
    5. Build CandidateProfile objects combining form + resume data
    6. Save profiles as JSON

    Args:
        use_llm: If True, attempts LLM-enhanced extraction.
        llm_model: OpenAI model name.
        output_dir: Directory to save profile JSONs. Defaults to data/profiles/.

    Returns:
        List of CandidateProfile objects.
    """
    from config.settings import get_settings

    settings = get_settings()

    if output_dir is None:
        output_dir = settings["DATA_DIR"] / "profiles"
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    resume_dir = settings["RESUME_DIR"]
    os.makedirs(resume_dir, exist_ok=True)

    # -- Step 1: Fetch sheet data --
    print("\n" + "=" * 60)
    print("  JOBPILOT - PHASE 2: RESUME PARSING PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print("\n Step 1: Fetching intake responses...")
    from src.jobpilot.intake.fetcher import fetch_all

    df = fetch_all()
    if df.empty:
        print("  [!]  No responses in sheet. Nothing to process.")
        return []

    print(f"  Found {len(df)} response(s)")

    # -- Step 2: Download resumes --
    print("\n Step 2: Downloading resume files...")

    resume_col = _find_resume_column(df)
    if not resume_col:
        print("  [!]  No 'Resume Upload' column found in sheet.")
        print(f"  Columns: {list(df.columns)}")
        print("  Skipping resume download.")
        drive_links = []
    else:
        drive_links = df[resume_col].tolist()
        print(f"  Found column: '{resume_col}'")

    download_results = download_all_resumes(drive_links, resume_dir)

    # Map resume link -> local path
    link_to_path = {}
    for link, path in download_results:
        link_to_path[link] = path

    # -- Load existing profiles for dedup --
    existing_by_email = {}
    if dedup_check:
        existing_by_email = _load_existing_profile_index(output_dir)
        if existing_by_email:
            print(f"  Found {len(existing_by_email)} existing profile(s) — will skip duplicates")

    # -- Steps 3-4: Extract + Analyze each resume --
    print("\n Step 3-4: Extracting and analyzing resumes...")

    profiles = []
    seen_emails: set[str] = set()       # intra-run dedup
    skip_count = 0

    for idx, row in df.iterrows():
        print(f"\n  {'-'*50}")
        print(f"  Processing response #{idx + 1}...")

        profile = CandidateProfile(
            full_name=_g(row, "Full Name"),
            date_of_birth="",
            phone=_g(row, "Phone Number"),
            email=_g(row, "Email Address"),
            current_city=_g(row, "Current City/ Location") or _g(row, "Current City / Location"),
            current_job_title=_g(row, "Current Job itle/Designation") or _g(row, "Current Job Title / Designation"),
            total_experience_years=_g(row, "Total Years of Experience "),
            current_company=_g(row, "Current Company "),
            notice_period=_g(row, "Notice period"),
            preferred_locations=_g(row, "Preferred Job Locations"),
            employment_type=_g(row, "Employment Type"),
            work_mode=_g(row, "Work Mode Preference"),
            seniority_level=_g(row, "Seniority Level"),
            preferred_roles=_g(row, "Preferred Job Role"),
            department=_g(row, "Department"),
            consent_resume_parsing=_g(row, "Consent for Resume Parsing"),
            consent_job_search=_g(row, "Consent for Automated Job Search"),
            consent_email=_g(row, "Consent for Email Delivery"),
            resume_drive_link=_g(row, resume_col) if resume_col else "",
            row_index=idx,
            timestamp=_g(row, "Timestamp"),
        )

        # Check consent (handles "I consent to..." full sentences)
        if not _check_consent(profile.consent_resume_parsing):
            print(f"      No consent for resume parsing -- skipping download + analysis")
            profiles.append(profile)
            continue

        # ── Dedup check: skip if we already have this SAME person (email + name) ──
        profile_email = profile.email.lower().strip() if profile.email else ""
        profile_name_key = profile.full_name.strip().lower() if profile.full_name else ""
        profile_key = (profile_email, profile_name_key)
        if profile_email and profile_name_key and dedup_check:
            if profile_key in existing_by_email or profile_key in seen_emails:
                existing_path = existing_by_email.get(profile_key, "(earlier in this batch)")
                print(f"      Duplicate detected: '{profile.full_name}' <{profile.email}> already exists")
                print(f"      Existing profile: {existing_path}")
                print(f"      Skipping this response entirely")
                skip_count += 1
                continue          # don't append to profiles at all
            seen_emails.add(profile_key)

        # Download (if not already mapped)
        local_path = link_to_path.get(profile.resume_drive_link) if profile.resume_drive_link else None
        if not local_path:
            print(f"      No resume link or download failed -- skipping analysis")
            profiles.append(profile)
            continue

        # Extract text
        print(f"     Extracting: {Path(local_path).name}")
        text = extract_text(local_path)
        if not text.strip():
            print(f"    [!]  No text extracted (scanned/image PDF?)")
            profiles.append(profile)
            continue

        # Analyze
        if use_llm:
            parsed = analyze_with_llm(text, file_name=Path(local_path).name, model=llm_model)
        else:
            parsed = analyze_resume(text, file_name=Path(local_path).name)

        profile.parsed_resume = parsed

        # Print summary
        print(f"     {parsed.full_name or '(name not detected)'}")
        print(f"     {parsed.email or '(email not detected)'}")
        print(f"      {len(parsed.skills)} skills, {len(parsed.work_experiences)} experiences, {len(parsed.education)} education entries")

        profiles.append(profile)

    # -- Step 5: Save profiles --
    print(f"\n Step 5: Saving profiles...")
    saved = _save_profiles(profiles, output_dir)

    # -- Summary --
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  New responses: {len(profiles)} candidate(s)")
    print(f"  Skipped (duplicate): {skip_count}")
    print(f"  Resumes successfully parsed: {sum(1 for p in profiles if p.parsed_resume is not None)}")
    print(f"  Profiles saved: {saved}")
    print(f"{'=' * 60}\n")

    return profiles


def _load_existing_profile_index(profiles_dir: Path) -> dict[tuple[str, str], str]:
    """Scan saved profile JSONs and build (email, name) -> filename index.

    Returns:
        dict mapping ``(lowercase_email, lowercase_name)`` tuple to profile filename.
        Both email and name must be present for a key to be created.
    """
    import json

    index: dict[tuple[str, str], str] = {}
    if not profiles_dir.exists():
        return index

    for fpath in sorted(profiles_dir.glob("profile_*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Try combined dict first (has richer data), fallback to form_data
        combined = data.get("combined") or data.get("form_data") or {}
        email = (combined.get("email") or "").strip().lower()
        name = (combined.get("full_name") or "").strip().lower()

        if email and name:
            index[(email, name)] = fpath.name

        # Also check form_data top-level email if combined didn't have it
        if not email and "form_data" in data and isinstance(data["form_data"], dict):
            fd = data["form_data"]
            email2 = (fd.get("email") or "").strip().lower()
            name2 = (fd.get("full_name") or "").strip().lower()
            if email2 and name2:
                index[(email2, name2)] = fpath.name

    return index


def _find_resume_column(df) -> str | None:
    """Find the resume upload column regardless of exact naming.
    Prefers columns with 'upload' AND 'resume' to avoid matching consent columns."""
    cols = [c.strip() for c in df.columns]

    # Strong match: contains both 'resume' and 'upload'
    for col in cols:
        cl = col.lower()
        if "resume" in cl and "upload" in cl:
            return col

    # Medium match: has 'upload' (drive link type)
    for col in cols:
        cl = col.lower()
        if "upload" in cl or "file" in cl or "cv" in cl:
            return col

    # Weak match: has 'resume' but NOT 'consent'
    for col in cols:
        cl = col.lower()
        if "resume" in cl and "consent" not in cl:
            return col

    return None


def _g(row, col, default=""):
    """Safe getter for DataFrame rows - matches by substring when exact match fails."""
    # Try exact match first
    if col in row.index:
        val = row[col]
    else:
        # Fallback: find a column that contains the target text (case-insensitive)
        col_lower = col.strip().lower()
        matched = None
        for c in row.index:
            if col_lower in c.strip().lower():
                matched = c
                break
        if matched:
            val = row[matched]
        else:
            return default

    if val is None or (isinstance(val, float) and val != val):  # NaN check
        return default
    return str(val).strip()


def _check_consent(val: str) -> bool:
    """Check if a consent field value is positive (yes / checked / full sentence)."""
    v = val.strip().lower()
    positive_words = ["yes", "y", "true", "agree", "consent", "authorize"]
    return any(w in v for w in positive_words)


def _save_profiles(profiles: list[CandidateProfile], output_dir: Path) -> int:
    """Save each profile as a JSON file. Returns count saved."""
    import json

    saved = 0
    for p in profiles:
        data = {
            "form_data": {
                "full_name": p.full_name,
                "email": p.email,
                "phone": p.phone,
                "current_city": p.current_city,
                "current_job_title": p.current_job_title,
                "total_experience_years": p.total_experience_years,
                "current_company": p.current_company,
                "notice_period": p.notice_period,
                "preferred_locations": p.preferred_locations,
                "employment_type": p.employment_type,
                "work_mode": p.work_mode,
                "seniority_level": p.seniority_level,
                "preferred_roles": p.preferred_roles,
                "department": p.department,
                "consents": {
                    "resume_parsing": p.consent_resume_parsing,
                    "job_search": p.consent_job_search,
                    "email": p.consent_email,
                },
            },
            "combined": p.combine(),
            "parsed_at": datetime.now().isoformat(),
        }

        sanitized_name = p.full_name.replace(" ", "_") if p.full_name else f"candidate_{p.row_index}"
        filename = output_dir / f"profile_{sanitized_name}_{p.row_index}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        saved += 1
        print(f"    [OK] {filename.name}")

    return saved
