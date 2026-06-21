# JobPilot – Run Configuration
"""
Environment-based configuration loader.
Reads .env from project root and exposes settings as a dict.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# Locate project root (parent of config/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    load_dotenv()  # fallback to default


def get_settings():
    """Return a dictionary of all project settings."""
    return {
        "SHEET_CSV_URL": os.getenv("SHEET_CSV_URL", ""),
        "DATA_DIR": PROJECT_ROOT / "data",
        "LOG_DIR": PROJECT_ROOT / "logs",
        "BACKUP_DIR": PROJECT_ROOT / "data" / "backups",
        "RESUME_DIR": PROJECT_ROOT / "data" / "resumes",
    }


def get_project_root():
    return PROJECT_ROOT
