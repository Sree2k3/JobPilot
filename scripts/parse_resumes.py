#!/usr/bin/env python3
"""
Entry-point script for Phase 2 – Resume Parsing Pipeline.

Usage:
    python scripts/parse_resumes.py              # local extraction only
    python scripts/parse_resumes.py --llm        # LLM-enhanced extraction (requires OPENAI_API_KEY)
    python scripts/parse_resumes.py --llm --model gpt-4o-mini
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.parser.pipeline import run_pipeline


def main():
    args = sys.argv[1:]

    use_llm = "--llm" in args
    model = "gpt-4o-mini"

    # Check for custom model
    for i, a in enumerate(args):
        if a == "--model" and i + 1 < len(args):
            model = args[i + 1]

    profiles = run_pipeline(use_llm=use_llm, llm_model=model)

    if not profiles:
        print("No candidates processed.")
        sys.exit(0)

    parsed_count = sum(1 for p in profiles if p.parsed_resume is not None)
    print(f"\n📊 Summary: {len(profiles)} candidates, {parsed_count} resumes parsed.")


if __name__ == "__main__":
    main()
