"""Document text extraction.

Supports PDF (``pypdf``), DOCX (``python-docx``) and plain text. Extraction is
deliberately defensive: uploaded bytes are untrusted, so we sniff magic bytes
rather than trusting the extension, never execute anything from the file, and
turn every parser failure into a typed :class:`ExtractionError`.

Text is returned as an ordered list of :class:`ExtractedSection` objects. Each
section carries a page number where the format provides one, which is what makes
page-level citations possible for PDFs.
"""

from __future__ import annotations

import codecs
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..core.errors import ExtractionError, UnsupportedFileError

# Magic numbers used for content sniffing.
PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


@dataclass
class ExtractedSection:
    """A contiguous run of text from one page (or the whole file for TXT)."""

    page: Optional[int]
    text: str
    index: int = 0


@dataclass
class ExtractionResult:
    sections: List[ExtractedSection] = field(default_factory=list)
    page_count: Optional[int] = None
    char_count: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections if section.text.strip())


# ---------------------------------------------------------------------------
# Format sniffing
# ---------------------------------------------------------------------------


def detect_format(data: bytes) -> str:
    """Detect the real format from the bytes alone.

    Raises :class:`UnsupportedFileError` when the payload matches nothing we can
    safely parse. The extension is never consulted here.
    """
    head = data[:8]

    if head.startswith(PDF_MAGIC):
        return "pdf"

    if head.startswith(ZIP_MAGIC):
        # A .docx is an OOXML zip; verify the document body part actually exists.
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:  # pragma: no cover - defensive
            raise UnsupportedFileError("The uploaded file is a corrupt archive.") from exc
        if "word/document.xml" in names:
            return "docx"
        raise UnsupportedFileError(
            "This file is a ZIP archive without a Word document body, so it is not a DOCX file."
        )

    if _looks_like_text(data):
        return "txt"

    raise UnsupportedFileError("Only PDF, TXT and DOCX files are supported.")


def sniff_format(data: bytes, extension: str) -> str:
    """Return the canonical format of ``data``, verifying it against ``extension``.

    Detection is content-based; the extension is then required to *agree* with
    what was detected. A text file renamed to ``.pdf`` (or a PDF renamed to
    ``.txt``) is rejected with an actionable message rather than being parsed as
    something it is not -- extensions are a claim, and untrusted claims are not
    honoured.
    """
    extension = (extension or "").lower()
    declared = extension.lstrip(".")
    detected = detect_format(data)

    if declared != detected:
        if not declared:
            raise UnsupportedFileError(
                f"The file has no extension but its contents are {detected.upper()}. "
                f"Rename it with the '.{detected}' extension and upload it again."
            )
        raise UnsupportedFileError(
            f"The contents of this file are {detected.upper()} but the extension is "
            f"'.{declared}'. Rename the file to '.{detected}' and upload it again."
        )
    return detected


#: How much of the payload to inspect when deciding whether it is text.
_TEXT_SAMPLE_BYTES = 8192
#: Fraction of the sample that must be printable for the payload to count as text.
_MIN_PRINTABLE_RATIO = 0.85


def _looks_like_text(data: bytes) -> bool:
    """Heuristic text detection that tolerates legacy encodings (cp1252, latin-1).

    A NUL byte anywhere in the sample is a hard "no" (no text format we accept
    contains NUL), and otherwise we require most of the sample to be printable
    characters. Decoding as latin-1 never fails, so control characters are the
    signal we act on rather than codec errors.
    """
    sample = data[:_TEXT_SAMPLE_BYTES]
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    text = sample.decode("latin-1")
    printable = sum(1 for char in text if char in "\t\n\r\f\v" or char.isprintable())
    return (printable / len(text)) >= _MIN_PRINTABLE_RATIO


# ---------------------------------------------------------------------------
# Whitespace normalisation
# ---------------------------------------------------------------------------

_HORIZONTAL_WS = re.compile(r"[ \t\u00a0]+")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")


def normalise_text(text: str) -> str:
    """Collapse noisy whitespace while preserving paragraph structure.

    Keeps single blank lines between paragraphs, removes hard-wrap artefacts
    inside a paragraph, and strips control characters that PDF extractors
    occasionally emit.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    text = _HORIZONTAL_WS.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _EXCESS_NEWLINES.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Per-format extractors
# ---------------------------------------------------------------------------


def _extract_pdf(data: bytes, max_pages: int, warnings: List[str]) -> ExtractionResult:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except PdfReadError as exc:
        raise ExtractionError(f"Could not read the PDF: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - pypdf raises a wide variety
        raise ExtractionError("Could not read the PDF file.") from exc

    if getattr(reader, "is_encrypted", False):
        # Try an empty password first; many PDFs are "encrypted" but unprotected.
        try:
            if reader.decrypt("") == 0:
                raise ExtractionError("This PDF is password protected and cannot be processed.")
        except ExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("This PDF is password protected and cannot be processed.") from exc

    total_pages = len(reader.pages)
    if total_pages > max_pages:
        warnings.append(
            f"PDF has {total_pages} pages; only the first {max_pages} were processed (configured limit)."
        )
    limit = min(total_pages, max_pages)

    result = ExtractionResult(page_count=total_pages)
    empty_pages = 0
    for number in range(limit):
        try:
            raw = reader.pages[number].extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - one bad page must not kill the job
            warnings.append(f"Page {number + 1} could not be extracted ({type(exc).__name__}).")
            raw = ""
        text = normalise_text(raw)
        if not text:
            empty_pages += 1
        result.sections.append(ExtractedSection(page=number + 1, text=text))

    if empty_pages:
        warnings.append(
            f"{empty_pages} page(s) contained no extractable text (likely scanned images; OCR is not enabled)."
        )
    result.char_count = sum(len(section.text) for section in result.sections)
    if result.char_count == 0:
        raise ExtractionError(
            "No text could be extracted from this PDF. It may be a scanned document; OCR is not enabled."
        )
    return result


def _extract_docx(data: bytes) -> ExtractionResult:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency is required
        raise ExtractionError("DOCX support requires python-docx to be installed.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - python-docx raises various errors
        raise ExtractionError("Could not read the DOCX file.") from exc

    blocks: List[str] = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))

    text = normalise_text("\n".join(blocks))
    if not text:
        raise ExtractionError("The DOCX file contains no readable text.")

    return ExtractionResult(
        sections=[ExtractedSection(page=None, text=text)],
        page_count=None,
        char_count=len(text),
    )


def _decode_text(data: bytes) -> str:
    """Decode a plain-text upload, honouring BOMs before guessing an encoding.

    UTF-16 is only attempted when a BOM proves it: any even-length byte string is
    *valid* UTF-16, so trying it as a fallback silently turns a cp1252 file into
    mojibake instead of raising.
    """
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 cannot fail, so this is unreachable in practice; kept as a guard.
    return data.decode("latin-1", errors="replace")


def _extract_txt(data: bytes) -> ExtractionResult:
    text = normalise_text(_decode_text(data))
    if not text:
        raise ExtractionError("The text file is empty.")
    return ExtractionResult(
        sections=[ExtractedSection(page=None, text=text)],
        page_count=None,
        char_count=len(text),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract(path: Path, max_pages: int, max_chars: int, add_warning) -> ExtractionResult:
    """Extract text from a stored upload.

    ``add_warning`` is a callback used to report non-fatal notes (e.g. truncated
    content) back to the pipeline so they surface in the UI.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExtractionError(f"The uploaded file could not be read: {exc.strerror or exc}") from exc

    if not data:
        raise ExtractionError("The uploaded file is empty.")

    fmt = sniff_format(data, path.suffix)
    warnings: List[str] = []

    if fmt == "pdf":
        result = _extract_pdf(data, max_pages=max_pages, warnings=warnings)
    elif fmt == "docx":
        result = _extract_docx(data)
    else:
        result = _extract_txt(data)

    result.warnings = warnings
    for warning in warnings:
        add_warning(warning)

    if result.char_count > max_chars:
        raise ExtractionError(
            f"Extracted text exceeds the configured limit of {max_chars:,} characters. "
            "Increase MAX_EXTRACTED_CHARS to process this document."
        )
    return result
