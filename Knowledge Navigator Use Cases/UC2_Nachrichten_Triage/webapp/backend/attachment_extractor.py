# backend/attachment_extractor.py
from __future__ import annotations
import io

# Only OOXML (.docx) is supported; legacy binary .doc (application/msword) is not.
DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def extract_text(data: bytes, mime_type: str) -> str:
    """Return plain text from PDF or DOCX bytes. Returns '' for unsupported types."""
    if mime_type == "application/pdf":
        return _extract_pdf(data)
    if mime_type in DOCX_MIME_TYPES:
        return _extract_docx(data)
    return ""


def _extract_pdf(data: bytes) -> str:
    import pdfplumber
    try:
        parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_docx(data: bytes) -> str:
    import docx
    try:
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""
