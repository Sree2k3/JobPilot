"""Download resume files from Google Drive links to local storage."""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def extract_file_id(url: str) -> str | None:
    """
    Extract a Google Drive file ID from various URL formats.

    Supported formats:
      - https://drive.google.com/file/d/FILE_ID/view
      - https://drive.google.com/open?id=FILE_ID
      - https://drive.google.com/uc?id=FILE_ID
      - Shortened: https://docs.google.com/uc?id=FILE_ID
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    # Pattern 1: /file/d/FILE_ID/view
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)

    # Pattern 2: id=FILE_ID in query params
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]

    # Pattern 3: /uc?export=download&id=FILE_ID
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)

    return None


def download_resume(drive_url: str, output_dir: str | Path) -> str | None:
    """
    Download a resume from a Google Drive link.

    Args:
        drive_url: The Google Drive URL from the sheet.
        output_dir: Directory to save the downloaded file.

    Returns:
        Path to the downloaded file, or None on failure.
    """
    file_id = extract_file_id(drive_url)
    if not file_id:
        print(f"    [!]  Could not extract file ID from URL: {drive_url[:60]}...")
        return None

    os.makedirs(output_dir, exist_ok=True)
    output_path = str(Path(output_dir) / f"{file_id}")

    try:
        import gdown

        downloaded_path = gdown.download(
            f"https://drive.google.com/uc?id={file_id}",
            output=output_path,
            quiet=True,
        )

        if not downloaded_path:
            print(f"    [!]  gdown returned None (file may not be accessible)")
            return None

        # If downloaded file has no extension, detect it from magic bytes
        path_obj = Path(downloaded_path)
        if not path_obj.suffix:
            ext = _detect_extension(downloaded_path)
            if ext:
                new_path = path_obj.with_suffix(ext)
                path_obj.rename(new_path)
                downloaded_path = str(new_path)
                print(f"    [OK] Downloaded -> {downloaded_path} (detected {ext})")
            else:
                print(f"    [!]  Downloaded file has unknown type, saved as-is")
        else:
            print(f"    [OK] Downloaded -> {downloaded_path}")

        return downloaded_path

    except Exception as e:
        print(f"    [X] Download failed: {e}")
        return None


def _detect_extension(filepath: str) -> str | None:
    """Detect file extension from magic bytes."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)

        # PDF
        if header.startswith(b"%PDF"):
            return ".pdf"

        # DOCX / OOXML (ZIP-based)
        if header.startswith(b"PK"):
            # Check for [Content_Types].xml inside (DOCX marker)
            import zipfile
            try:
                with zipfile.ZipFile(filepath) as z:
                    names = z.namelist()
                    if any("word/" in n for n in names):
                        return ".docx"
                    return ".zip"
            except zipfile.BadZipFile:
                pass

        # DOC (older format - magic bytes)
        if header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
            return ".doc"

        return None
    except Exception:
        return None


def download_all_resumes(
    drive_links: list[str],
    output_dir: str | Path,
    skip_existing: bool = True,
) -> list[tuple[str, str | None]]:
    """
    Download multiple resume files from a list of Drive links.

    Args:
        drive_links: List of Google Drive URLs.
        output_dir: Directory to save files.
        skip_existing: If True, skip files already downloaded.

    Returns:
        List of (drive_url, local_path_or_None) tuples.
    """
    results = []
    for link in drive_links:
        if not link or pdna(link):
            results.append((link, None))
            continue

        file_id = extract_file_id(link)
        if file_id and skip_existing:
            existing = list(Path(output_dir).glob(f"{file_id}.*"))
            if existing:
                print(f"      Already exists -> {existing[0]}")
                results.append((link, str(existing[0])))
                continue

        path = download_resume(link, output_dir)
        results.append((link, path))

    return results


def pdna(val) -> bool:
    """Check if a value is pandas NaN / None / empty."""
    import pandas as pd
    return val is None or (isinstance(val, float) and pd.isna(val)) or val == ""
