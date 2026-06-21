"""Analyze resume text using local pattern-matching or LLM enhancement.

Supports two modes:
  1. Local extractor (default) - regex + keyword patterns, no API key required.
  2. LLM enhancer - uses OpenAI to extract structured data when OPENAI_API_KEY is set.
"""

import os
import re
from typing import Optional

from .models import ParsedResume, WorkExperience, Education

# ----------------------------------------------
#  COMMON RESUME SECTION HEADERS
# ----------------------------------------------
SECTION_HEADERS = {
    "summary": [
        r"(?i)^(professional\s+)?summary\b",
        r"(?i)^(career\s+)?objective\b",
        r"(?i)^profile\b",
        r"(?i)^about\s+me\b",
    ],
    "experience": [
        r"(?i)^(professional\s+)?experience\b",
        r"(?i)^work\s+(experience|history)\b",
        r"(?i)^employment\s+(history|experience)\b",
        r"(?i)^relevant\s+experience\b",
    ],
    "education": [
        r"(?i)^education\b",
        r"(?i)^academic\s+(background|qualifications)\b",
    ],
    "skills": [
        r"(?i)^(technical\s+)?skills\b",
        r"(?i)^core\s+competencies?\b",
        r"(?i)^areas?\s+of\s+expertise\b",
    ],
    "certifications": [
        r"(?i)^certifications?\b",
        r"(?i)^licenses?\b",
        r"(?i)^professional\s+(certifications|development)\b",
    ],
    "projects": [
        r"(?i)^projects?\b",
        r"(?i)^(key\s+)?projects?\b",
    ],
    "languages": [
        r"(?i)^languages?\b",
    ],
}


def analyze_resume(text: str, file_name: str = "") -> ParsedResume:
    """
    Extract structured data from resume text using local pattern matching.

    Args:
        text: Raw text extracted from the resume file.
        file_name: Original file name (for metadata).

    Returns:
        A ParsedResume instance.
    """
    result = ParsedResume(raw_text=text, file_name=file_name)

    if not text or not text.strip():
        print("    [!]  Empty text -- nothing to analyze")
        return result

    # -- Contact info --
    result.full_name = _extract_name(text)
    result.email = _extract_email(text)
    result.phone = _extract_phone(text)
    result.location = _extract_location(text)
    result.linkedin_url = _extract_url(text, "linkedin")
    result.portfolio_url = _extract_url(text, r"github|portfolio|github\.io")

    # -- Sections --
    sections = _split_sections(text)

    # Professional summary
    result.professional_summary = _extract_summary(sections)

    # Work experience
    result.work_experiences, result.total_experience_years = _extract_experience(sections)

    # Education
    result.education = _extract_education(sections)

    # Skills (both general and technical)
    result.skills, result.technical_skills = _extract_skills(sections)

    # Certifications
    result.certifications = _extract_certifications(sections)

    # Languages
    result.languages = _extract_languages(sections)

    return result


# ----------------------------------------------
#  CONTACT INFO EXTRACTION
# ----------------------------------------------

def _extract_name(text: str) -> str:
    """
    Heuristic: the first non-empty line at the top of the resume is often the name.
    Filters out common false positives.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    skip_phrases = [
        "resume", "curriculum vitae", "cv", "summary", "profile",
        "email", "phone", "contact", "experience", "education", "skills",
    ]

    for line in lines[:10]:
        line = line.strip()
        # Must be reasonably short for a name (5-40 chars)
        if 4 < len(line) < 45:
            # Must not be a known section header or contact term
            if not any(line.lower().startswith(p) for p in skip_phrases):
                # Must not be an email or URL
                if not re.search(r"[@©®]", line):
                    # Must not be ALL CAPS LONG (likely a header) unless it's short
                    if not (line.isupper() and len(line) > 25):
                        return line
    return ""


def _extract_email(text: str) -> str:
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    # Filter out non-personal/common domains if needed
    return emails[0] if emails else ""


def _extract_phone(text: str) -> str:
    patterns = [
        r"\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
        r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
    return ""


def _extract_location(text: str) -> str:
    # Look near "Location" or "Address" labels
    location_patterns = [
        r"(?i)(?:location|address|city|based)\s*[:;-]\s*(.+?)(?:\n|$)",
        r"(?i)^\s*([A-Za-z\s]+,\s*[A-Za-z\s]+)\s*$",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            loc = match.group(1).strip()
            if 3 < len(loc) < 60:
                return loc
    return ""


def _extract_url(text: str, domain: str) -> str:
    pattern = re.compile(
        rf"https?://(?:www\.)?(?:{domain})[^\s)\"'>]*", re.IGNORECASE
    )
    match = pattern.search(text)
    return match.group(0).strip("/") if match else ""


# ----------------------------------------------
#  SECTION SPLITTING
# ----------------------------------------------

def _split_sections(text: str) -> dict[str, str]:
    """Split resume text into sections by common headers."""
    lines = text.split("\n")
    section_map = {"_header": ""}
    current_section = "_header"

    for line in lines:
        matched = False
        for section_name, patterns in SECTION_HEADERS.items():
            for pat in patterns:
                if re.match(pat, line.strip()):
                    current_section = section_name
                    if current_section not in section_map:
                        section_map[current_section] = ""
                    matched = True
                    break
            if matched:
                break

        if not matched:
            section_map[current_section] += line + "\n"

    return section_map


def _get_section(sections: dict, name: str) -> str:
    return sections.get(name, "").strip()


# ----------------------------------------------
#  SUMMARY EXTRACTION
# ----------------------------------------------

def _extract_summary(sections: dict) -> str:
    summary = _get_section(sections, "summary")
    if summary:
        lines = [l.strip() for l in summary.split("\n") if l.strip()]
        return " ".join(lines)[:1000]
    return ""


# ----------------------------------------------
#  EXPERIENCE EXTRACTION
# ----------------------------------------------

def _extract_experience(sections: dict) -> tuple[list[WorkExperience], Optional[float]]:
    """Extract work experiences and total years from the experience section."""
    exp_text = _get_section(sections, "experience")
    if not exp_text:
        return [], None

    experiences = []
    blocks = re.split(r"\n\s*\n", exp_text)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 20:
            continue

        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        exp = WorkExperience()
        exp.job_title = lines[0] if len(lines) > 0 else ""
        exp.company = lines[1] if len(lines) > 1 else ""

        # Try to extract dates from the first 3 lines
        date_pattern = r"(\d{4})\s*[-to]+\s*(present|current|now|\d{4})"
        for line in lines[:3]:
            dm = re.search(date_pattern, line, re.IGNORECASE)
            if dm:
                exp.start_date = dm.group(1)
                end = dm.group(2).lower()
                if end in ("present", "current", "now"):
                    exp.end_date = "Present"
                else:
                    exp.end_date = end
                break

        # Remaining lines go to description (skip date lines)
        desc_lines = []
        for line in lines[2:]:
            if not re.search(r"\d{4}\s*[-to]", line):
                desc_lines.append(line)
        exp.description = " ".join(desc_lines)[:1000]

        experiences.append(exp)

    # Extract total years from text
    total_years = _extract_total_years(exp_text)
    for exp in experiences:
        if exp.start_date and exp.end_date and exp.end_date != "Present":
            try:
                exp.duration_years = max(0, int(exp.end_date) - int(exp.start_date))
            except ValueError:
                pass

    return experiences, total_years


def _extract_total_years(text: str) -> Optional[float]:
    """Look for explicit 'X years of experience' patterns."""
    patterns = [
        r"(?i)(\d+[+]?)\s*\+?\s*years?\s+(of\s+)?experience",
        r"(?i)total\s+experience[:\s]+(\d+[+]?)\s*years?",
        r"(?i)(\d+[+]?)\s*yr?s?\s+(of\s+)?exp",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = m.group(1).replace("+", "")
            try:
                return float(val)
            except ValueError:
                pass
    return None


# ----------------------------------------------
#  EDUCATION EXTRACTION
# ----------------------------------------------

def _extract_education(sections: dict) -> list[Education]:
    edu_text = _get_section(sections, "education")
    if not edu_text:
        return []

    entries = []
    blocks = re.split(r"\n\s*\n", edu_text)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 10:
            continue

        edu = Education()
        lines = [l.strip() for l in block.split("\n") if l.strip()]

        if lines:
            edu.degree = lines[0]
        if len(lines) > 1:
            edu.institution = lines[1]

        # Extract years
        years = re.findall(r"\b(19\d{2}|20\d{2})\b", block)
        if years:
            edu.start_year = years[0]
            edu.end_year = years[-1] if len(years) > 1 else years[0]

        entries.append(edu)

    return entries


# ----------------------------------------------
#  SKILLS EXTRACTION
# ----------------------------------------------

# Common tech skills for detection
COMMON_TECH_SKILLS = [
    # Languages
    "python", "javascript", "typescript", "java", "c\\+?\\+?", "c#", "go", "rust",
    "swift", "kotlin", "ruby", "php", "scala", "r", "sql", "bash", "shell",
    "dart", "elixir", "perl", "lua",
    # Web
    "react", "angular", "vue", "node\\.?js", "express", "django", "flask",
    "spring", "fastapi", "html", "css", "sass", "tailwind", "bootstrap",
    "next\\.?js", "nuxt\\.?js", "svelte", "jquery",
    # Cloud & DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins",
    "circleci", "github actions", "gitlab ci", "ansible", "pulumi",
    # Data & AI
    "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn", "spark",
    "hadoop", "airflow", "kafka", "langchain", "llm", "nlp", "opencv",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra",
    "dynamodb", "firebase", "supabase",
    # Tools
    "git", "linux", "vim", "vscode", "jira", "confluence", "figma",
    "postman", "swagger", "grafana", "prometheus",
    # Mobile
    "flutter", "react native", "android", "ios",
]


def _extract_skills(sections: dict) -> tuple[list[str], list[str]]:
    """Extract all skills and separate technical skills."""
    skill_text = _get_section(sections, "skills")
    if not skill_text:
        return [], []

    # Also grab skills from the full text for marking
    all_text = skill_text

    # Split by common delimiters
    raw_skills = re.split(r"[*·,;|\n]+", all_text)
    raw_skills = [s.strip().strip("*· \t") for s in raw_skills if s.strip()]
    raw_skills = [s for s in raw_skills if 1 < len(s) < 60]

    # Classify
    all_skills = []
    tech_skills = []

    for skill in raw_skills:
        skill_lower = skill.lower().strip()
        all_skills.append(skill)

        # Check if it matches known tech skills
        for tech in COMMON_TECH_SKILLS:
            if re.fullmatch(tech, skill_lower, re.IGNORECASE):
                tech_skills.append(skill)
                break

    # Deduplicate while preserving order
    seen = set()
    all_skills_uniq = []
    for s in all_skills:
        if s.lower() not in seen:
            seen.add(s.lower())
            all_skills_uniq.append(s)

    seen_tech = set()
    tech_skills_uniq = []
    for s in tech_skills:
        if s.lower() not in seen_tech:
            seen_tech.add(s.lower())
            tech_skills_uniq.append(s)

    return all_skills_uniq, tech_skills_uniq


# ----------------------------------------------
#  CERTIFICATIONS & LANGUAGES
# ----------------------------------------------

def _extract_certifications(sections: dict) -> list[str]:
    cert_text = _get_section(sections, "certifications")
    if not cert_text:
        return []
    lines = [l.strip().strip("*·-") for l in cert_text.split("\n") if l.strip()]
    return [l for l in lines if 2 < len(l) < 100]


def _extract_languages(sections: dict) -> list[str]:
    lang_text = _get_section(sections, "languages")
    if not lang_text:
        return []
    lines = [l.strip().strip("*·-") for l in lang_text.split("\n") if l.strip()]
    return [l for l in lines if 2 < len(l) < 50]


# ----------------------------------------------
#  LLM-ENHANCED EXTRACTION (optional)
# ----------------------------------------------

def analyze_with_llm(text: str, file_name: str = "", model: str = "gpt-4o-mini") -> ParsedResume:
    """
    Use OpenAI to deeply extract structured data from resume text.
    Falls back to local extraction if OPENAI_API_KEY is not set or if the call fails.

    Args:
        text: Raw resume text.
        file_name: Original file name.
        model: OpenAI model to use.

    Returns:
        ParsedResume with LLM-enhanced fields.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("    [!]  No OPENAI_API_KEY found -- using local extraction instead")
        return analyze_resume(text, file_name)

    # Start with local extraction as a baseline
    local_result = analyze_resume(text, file_name)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        prompt = f"""You are a resume parser. Extract structured information from the resume text below.

Return your answer as a JSON object with these keys:
- full_name: str
- email: str
- phone: str
- location: str
- linkedin_url: str
- portfolio_url: str
- professional_summary: str (2-3 sentence summary)
- skills: list[str] (all skills mentioned)
- technical_skills: list[str] (programming languages, frameworks, tools, cloud)
- total_experience_years: float or null
- work_experiences: list of {{job_title, company, start_date, end_date, duration_years, description}}
- education: list of {{degree, institution, field_of_study, start_year, end_year}}
- certifications: list[str]
- languages: list[str]

Resume text:
---
{text[:12000]}
---
JSON:"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise resume parser. Extract all requested fields as valid JSON. Use null for missing values.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )

        import json

        raw = response.choices[0].message.content
        data = json.loads(raw)

        # Map LLM response into ParsedResume, using local data as fallback
        result = ParsedResume(
            full_name=data.get("full_name") or local_result.full_name,
            email=data.get("email") or local_result.email,
            phone=data.get("phone") or local_result.phone,
            location=data.get("location") or local_result.location,
            linkedin_url=data.get("linkedin_url") or local_result.linkedin_url,
            portfolio_url=data.get("portfolio_url") or local_result.portfolio_url,
            professional_summary=data.get("professional_summary") or local_result.professional_summary,
            skills=data.get("skills", local_result.skills),
            technical_skills=data.get("technical_skills", local_result.technical_skills),
            total_experience_years=data.get("total_experience_years") or local_result.total_experience_years,
            work_experiences=[
                WorkExperience(**exp) for exp in data.get("work_experiences", [])
            ] or local_result.work_experiences,
            education=[
                Education(**edu) for edu in data.get("education", [])
            ] or local_result.education,
            certifications=data.get("certifications", local_result.certifications),
            languages=data.get("languages", local_result.languages),
            raw_text=text,
            file_name=file_name,
        )

        print(f"     LLM extraction complete ({len(result.skills)} skills, {len(result.work_experiences)} experiences)")
        return result

    except Exception as e:
        print(f"    [!]  LLM extraction failed: {e}")
        print(f"    [!]  Falling back to local extraction")
        return local_result
