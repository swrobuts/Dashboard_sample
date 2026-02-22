# tests/test_attachment_extractor.py
import pytest
from backend.attachment_extractor import extract_text


def test_extract_pdf_returns_text(mocker):
    """_extract_pdf joins non-None page texts with newlines."""
    import pdfplumber  # ensure module is in sys.modules so patch works
    mock_page1 = mocker.MagicMock()
    mock_page1.extract_text.return_value = "Seite 1"
    mock_page2 = mocker.MagicMock()
    mock_page2.extract_text.return_value = None   # blank page — must be excluded
    mock_ctx = mocker.MagicMock()
    mock_ctx.__enter__ = mocker.MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = mocker.MagicMock(return_value=False)
    mock_ctx.pages = [mock_page1, mock_page2]
    mocker.patch("pdfplumber.open", return_value=mock_ctx)

    result = extract_text(b"fake-pdf", "application/pdf")
    assert result == "Seite 1"


def test_extract_docx_returns_text(mocker):
    """_extract_docx joins non-empty paragraphs with newlines."""
    import docx  # ensure in sys.modules
    mock_p1 = mocker.MagicMock(); mock_p1.text = "Erster Absatz"
    mock_p2 = mocker.MagicMock(); mock_p2.text = ""   # blank — must be excluded
    mock_p3 = mocker.MagicMock(); mock_p3.text = "Dritter Absatz"
    mock_doc = mocker.MagicMock()
    mock_doc.paragraphs = [mock_p1, mock_p2, mock_p3]
    mocker.patch("docx.Document", return_value=mock_doc)

    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    result = extract_text(b"fake-docx", mime)
    assert result == "Erster Absatz\nDritter Absatz"


def test_extract_msword_also_supported(mocker):
    """application/msword is also handled as DOCX."""
    import docx
    mock_doc = mocker.MagicMock()
    mock_doc.paragraphs = []
    mocker.patch("docx.Document", return_value=mock_doc)

    result = extract_text(b"fake", "application/msword")
    assert result == ""   # no paragraphs → empty, but no exception


def test_extract_unknown_mime_returns_empty():
    """Unsupported MIME types return empty string without error."""
    assert extract_text(b"data", "image/jpeg") == ""
    assert extract_text(b"data", "text/plain") == ""
