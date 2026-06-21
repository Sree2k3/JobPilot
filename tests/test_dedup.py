"""Tests for the deduplication logic in the pipeline."""

import sys
import json
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.jobpilot.parser.pipeline import _load_existing_profile_index


def test_load_index_empty_dir():
    """Empty directory should return an empty index."""
    with tempfile.TemporaryDirectory() as tmp:
        index = _load_existing_profile_index(Path(tmp))
        assert index == {}


def test_load_index_no_json():
    """Directory with no matching profile JSONs should return empty."""
    with tempfile.TemporaryDirectory() as tmp:
        # Write a non-profile file
        (Path(tmp) / "other.json").write_text('{"email": "a@b.com"}', encoding="utf-8")
        index = _load_existing_profile_index(Path(tmp))
        assert index == {}


def test_load_index_single_profile():
    """Single profile with email + name in combined dict is indexed."""
    with tempfile.TemporaryDirectory() as tmp:
        profile = {
            "form_data": {"email": "alice@example.com", "full_name": "Alice"},
            "combined": {"email": "alice@example.com", "full_name": "Alice", "skills": []},
        }
        fpath = Path(tmp) / "profile_Alice_0.json"
        fpath.write_text(json.dumps(profile), encoding="utf-8")

        index = _load_existing_profile_index(Path(tmp))
        assert index == {("alice@example.com", "alice"): "profile_Alice_0.json"}


def test_load_index_form_data_fallback():
    """If combined dict is missing email, falls back to form_data."""
    with tempfile.TemporaryDirectory() as tmp:
        profile = {
            "form_data": {"email": "bob@test.com", "full_name": "Bob"},
            "combined": {"full_name": "Bob", "skills": []},  # no email in combined
        }
        fpath = Path(tmp) / "profile_Bob_0.json"
        fpath.write_text(json.dumps(profile), encoding="utf-8")

        index = _load_existing_profile_index(Path(tmp))
        assert index == {("bob@test.com", "bob"): "profile_Bob_0.json"}


def test_load_index_case_insensitive():
    """Email + name keys are stored lowercase."""
    with tempfile.TemporaryDirectory() as tmp:
        profile = {
            "form_data": {"email": "Alice.Wonderland@Example.Com", "full_name": "Alice"},
            "combined": {"full_name": "Alice", "email": "Alice.Wonderland@Example.Com"},
        }
        fpath = Path(tmp) / "profile_Alice_0.json"
        fpath.write_text(json.dumps(profile), encoding="utf-8")

        index = _load_existing_profile_index(Path(tmp))
        assert ("alice.wonderland@example.com", "alice") in index
        assert ("Alice.Wonderland@Example.Com", "Alice") not in index


def test_load_index_multiple_profiles():
    """Multiple profiles produce a multi-entry index keyed by (email, name)."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, email in [("Alice", "alice@x.com"), ("Bob", "bob@x.com")]:
            profile = {
                "form_data": {"email": email, "full_name": name},
                "combined": {"email": email, "full_name": name},
            }
            fpath = Path(tmp) / f"profile_{name}_0.json"
            fpath.write_text(json.dumps(profile), encoding="utf-8")

        index = _load_existing_profile_index(Path(tmp))
        assert len(index) == 2
        assert index[("alice@x.com", "alice")] == "profile_Alice_0.json"
        assert index[("bob@x.com", "bob")] == "profile_Bob_0.json"


def test_load_index_skips_corrupt_json():
    """Corrupt JSON files are gracefully skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "profile_Corrupt_0.json").write_text(
            "not valid json", encoding="utf-8"
        )
        (Path(tmp) / "profile_Good_0.json").write_text(
            json.dumps(
                {
                    "form_data": {"email": "good@x.com", "full_name": "Good"},
                    "combined": {"email": "good@x.com", "full_name": "Good"},
                }
            ),
            encoding="utf-8",
        )

        index = _load_existing_profile_index(Path(tmp))
        assert len(index) == 1
        assert index[("good@x.com", "good")] == "profile_Good_0.json"
