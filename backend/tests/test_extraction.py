"""Extraction tests: format sniffing, whitespace normalisation, per-format parsing."""

from __future__ import annotations

import io

import pytest

from app.core.errors import ExtractionError, UnsupportedFileError
from app.services.extraction import (
    extract,
    normalise_text,
    sniff_format,
)

from .conftest import make_docx, make_pdf, make_txt


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# Format sniffing -- bytes win over the extension
# ---------------------------------------------------------------------------


def test_sniff_pdf_from_magic_bytes():
    _name, data, _ct = make_pdf()
    assert sniff_format(data, ".pdf") == "pdf"


def test_sniff_docx_from_zip_container():
    _name, data, _ct = make_docx()
    assert sniff_format(data, ".docx") == "docx"


def test_sniff_plain_text():
    assert sniff_format(b"hello world", ".txt") == "txt"


def test_sniff_rejects_text_content_claiming_to_be_pdf():
    with pytest.raises(UnsupportedFileError):
        sniff_format(b"this is plain text, not a pdf", ".pdf")


def test_sniff_rejects_binary_garbage():
    with pytest.raises(UnsupportedFileError):
        sniff_format(b"\x00\x01\x02\x03binary", ".txt")


def test_sniff_rejects_zip_that_is_not_docx():
    archive = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("hello.txt", "not a word document")
    with pytest.raises(UnsupportedFileError):
        sniff_format(archive.getvalue(), ".docx")


def test_sniff_rejects_unknown_binary_format():
    with pytest.raises(UnsupportedFileError):
        sniff_format(b"\x89PNG\r\n\x1a\n", ".png")


# ---------------------------------------------------------------------------
# Whitespace normalisation
# ---------------------------------------------------------------------------


def test_normalise_collapses_hard_wraps_and_keeps_paragraphs():
    raw = "Line one   with   spaces\nLine two\r\n\n\n\n\nNew paragraph"
    assert normalise_text(raw) == "Line one with spaces\nLine two\n\nNew paragraph"


def test_normalise_strips_control_characters():
    assert normalise_text("alpha\x07beta\x00gamma") == "alphabetagamma"


def test_normalise_handles_empty_input():
    assert normalise_text("") == ""
    assert normalise_text("   ") == ""


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------


def test_extract_txt_roundtrip(tmp_path):
    _name, data, _ct = make_txt(text="Alpha beta.\n\nGamma delta.")
    result = extract(_write(tmp_path, "a.txt", data), max_pages=10, max_chars=10000, add_warning=lambda _m: None)
    assert result.char_count == len("Alpha beta.\n\nGamma delta.")
    assert "Gamma delta." in result.text


def test_extract_txt_handles_cp1252(tmp_path):
    warning: list[str] = []
    path = _write(tmp_path, "a.txt", "caf\u00e9 na\u00efve".encode("cp1252"))
    result = extract(path, max_pages=10, max_chars=10000, add_warning=warning.append)
    assert "caf" in result.text


def test_extract_empty_txt_raises(tmp_path):
    path = _write(tmp_path, "empty.txt", b"")
    with pytest.raises(ExtractionError):
        extract(path, max_pages=10, max_chars=10000, add_warning=lambda _m: None)


def test_extract_txt_exceeding_char_limit_raises(tmp_path):
    _name, data, _ct = make_txt(text="x" * 500)
    path = _write(tmp_path, "big.txt", data)
    with pytest.raises(ExtractionError) as error:
        extract(path, max_pages=10, max_chars=100, add_warning=lambda _m: None)
    assert "MAX_EXTRACTED_CHARS" in str(error.value)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def test_extract_pdf_preserves_page_numbers(tmp_path):
    _name, data, _ct = make_pdf(pages=["First page about the Wide Field Imager.", "Second page about the spectrometer."])
    result = extract(_write(tmp_path, "a.pdf", data), max_pages=10, max_chars=100000, add_warning=lambda _m: None)
    assert result.page_count == 2
    assert [section.page for section in result.sections] == [1, 2]
    assert "Wide Field Imager" in result.sections[0].text
    assert "spectrometer" in result.sections[1].text


def test_extract_pdf_reports_page_limit_warning(tmp_path):
    warnings: list[str] = []
    _name, data, _ct = make_pdf(pages=["one", "two", "three"])
    result = extract(_write(tmp_path, "a.pdf", data), max_pages=2, max_chars=100000, add_warning=warnings.append)
    assert result.page_count == 3
    assert len(result.sections) == 2
    assert any("only the first 2" in warning for warning in warnings)


def test_extract_pdf_without_text_raises(tmp_path):
    """A PDF with no text layer (i.e. a scan) must fail loudly, not silently index nothing."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.rect(10, 10, 100, 100)
    pdf.showPage()
    pdf.save()
    path = _write(tmp_path, "blank.pdf", buffer.getvalue())
    with pytest.raises(ExtractionError):
        extract(path, max_pages=10, max_chars=100000, add_warning=lambda _m: None)


def test_extract_corrupt_pdf_raises(tmp_path):
    path = _write(tmp_path, "broken.pdf", b"%PDF-1.4\nnot really a pdf at all\n")
    with pytest.raises(ExtractionError):
        extract(path, max_pages=10, max_chars=100000, add_warning=lambda _m: None)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def test_extract_docx_paragraphs_and_tables(tmp_path):
    _name, data, _ct = make_docx(paragraphs=["Alpha paragraph.", "Beta paragraph."])
    result = extract(_write(tmp_path, "a.docx", data), max_pages=10, max_chars=100000, add_warning=lambda _m: None)
    assert "Alpha paragraph." in result.text
    assert "Beta paragraph." in result.text
    assert "Parameter | Value" in result.text
    assert result.page_count is None


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(ExtractionError):
        extract(tmp_path / "nope.txt", max_pages=10, max_chars=1000, add_warning=lambda _m: None)
