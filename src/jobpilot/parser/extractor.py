"""Extract raw text from PDF and DOCX resume files."""

import os
import sys
from pathlib import Path


def extract_text(file_path: str | Path) -> str:
    """
    Extract text from a resume file (.pdf or .docx).

    If the file has no extension, tries to detect the type from magic bytes.

    Args:
        file_path: Path to the resume file.

    Returns:
        Extracted text content as a string.

    Raises:
        ValueError: If the file type is unsupported.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(path)
    elif suffix == ".docx":
        return _extract_docx(path)
    elif suffix == "":
        # No extension -- try sniffing magic bytes
        detected = _sniff_type(path)
        if detected == "pdf":
            return _extract_pdf(path)
        elif detected == "docx":
            return _extract_docx(path)
        else:
            raise ValueError(
                f"Unsupported file type (no extension, detected={detected}). "
                f"Expected .pdf or .docx"
            )
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Expected .pdf or .docx")


def _extract_pdf(path: Path) -> str:
    """Extract text from a PDF using pdfplumber (preferred) or PyPDF2 as fallback."""
    text_parts = []

    # Try pdfplumber first (better layout preservation)
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        if text_parts:
            return "\n\n".join(text_parts)
    except ImportError:
        pass
    except Exception as e:
        print(f"    [!]  pdfplumber failed: {e}. Trying PyPDF2...")

    # Fallback to PyPDF2
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        return "\n\n".join(text_parts)
    except ImportError:
        pass
    except Exception as e:
        print(f"    [!]  PyPDF2 also failed: {e}")

    if not text_parts:
        print(f"    [!]  No text extracted from PDF (may be scanned/image-based)")
        return ""

    return "\n\n".join(text_parts)


def _sniff_type(path: Path) -> str | None:
    """Sniff file type from magic bytes (no extension available)."""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        if header.startswith(b"%PDF"):
            return "pdf"
        if header.startswith(b"PK"):
            # Could be DOCX -- check for word/ inside
            try:
                import zipfile
                with zipfile.ZipFile(path) as z:
                    if any("word/" in n for n in z.namelist()):
                        return "docx"
            except Exception:
                pass
        return None
    except Exception:
        return None


def _extract_docx(path: Path) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document

        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        print("    [X] python-docx not installed. Install with: pip install python-docx")
        return ""
    except Exception as e:
        print(f"    [!]  Failed to extract DOCX: {e}")
        return ""


def extract_all(file_paths: list[str | Path]) -> dict[str, str]:
    """
    Extract text from multiple resume files.

    Args:
        file_paths: List of file paths.

    Returns:
        Dict mapping file path -> extracted text.
    """
    results = {}
    for fp in file_paths:
        print(f"   Extracting: {Path(fp).name}")
        try:
            text = extract_text(fp)
            results[str(fp)] = text
            char_count = len(text)
            print(f"    [OK] Extracted {char_count:,} characters")
        except Exception as e:
            print(f"    [X] {e}")
            results[str(fp)] = ""

    return results
