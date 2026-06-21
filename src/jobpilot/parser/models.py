"""Data models for parsed resume data and candidate profiles."""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class WorkExperience:
    """A single work experience entry."""
    job_title: str = ""
    company: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_years: Optional[float] = None
    description: str = ""
    skills_used: list[str] = field(default_factory=list)


@dataclass
class Education:
    """An education entry."""
    degree: str = ""
    institution: str = ""
    field_of_study: str = ""
    start_year: Optional[str] = None
    end_year: Optional[str] = None


@dataclass
class ParsedResume:
    """Structured data extracted from a resume file."""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""

    # Summary / headline
    professional_summary: str = ""

    # Skills
    skills: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    technical_skills: list[str] = field(default_factory=list)

    # Experience
    total_experience_years: Optional[float] = None
    work_experiences: list[WorkExperience] = field(default_factory=list)

    # Education
    education: list[Education] = field(default_factory=list)

    # Certifications
    certifications: list[str] = field(default_factory=list)

    # Languages
    languages: list[str] = field(default_factory=list)

    # Raw text (for fallback / search)
    raw_text: str = ""

    # Metadata
    file_name: str = ""
    parsed_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CandidateProfile:
    """
    Full candidate profile combining:
    - Form response fields (from the Google Sheet)
    - Parsed resume data (from the resume file)
    """
    # ── Intake form data ──
    full_name: str = ""
    date_of_birth: str = ""
    phone: str = ""
    email: str = ""
    current_city: str = ""
    current_job_title: str = ""
    total_experience_years: str = ""
    current_company: str = ""
    notice_period: str = ""
    preferred_locations: str = ""
    employment_type: str = ""
    work_mode: str = ""
    seniority_level: str = ""
    preferred_roles: str = ""
    consent_resume_parsing: str = ""
    consent_job_search: str = ""
    consent_email: str = ""
    resume_drive_link: str = ""

    # ── Parsed resume data (enriches / overrides form data) ──
    parsed_resume: Optional[ParsedResume] = None

    # ── Row metadata ──
    row_index: int = 0
    timestamp: str = ""

    def combine(self) -> dict:
        """Return a flat dict merging form + resume data for downstream use."""
        base = {
            "full_name": self.full_name or (self.parsed_resume.full_name if self.parsed_resume else ""),
            "email": self.email or (self.parsed_resume.email if self.parsed_resume else ""),
            "phone": self.phone or (self.parsed_resume.phone if self.parsed_resume else ""),
            "location": self.current_city or (self.parsed_resume.location if self.parsed_resume else ""),
            "current_job_title": self.current_job_title,
            "current_company": self.current_company,
            "total_experience_years": self.total_experience_years,
            "notice_period": self.notice_period,
            "preferred_locations": self.preferred_locations,
            "employment_type": self.employment_type,
            "work_mode": self.work_mode,
            "seniority_level": self.seniority_level,
            "preferred_roles": self.preferred_roles,
        }

        if self.parsed_resume:
            base["skills"] = self.parsed_resume.skills
            base["technical_skills"] = self.parsed_resume.technical_skills
            base["work_experiences"] = [
                asdict(exp) for exp in self.parsed_resume.work_experiences
            ]
            base["education"] = [
                asdict(edu) for edu in self.parsed_resume.education
            ]
            base["certifications"] = self.parsed_resume.certifications
            base["professional_summary"] = self.parsed_resume.professional_summary

        return base
