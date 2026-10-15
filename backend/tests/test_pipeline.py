"""Pipeline and upload-handling tests (service level, no HTTP)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ExtractionError, FileTooLargeError, UnsupportedFileError
from app.services.pipeline import (
    STAGE_DEFINITIONS,
    PipelineRunner,
    check_upload,
    compute_progress,
    persist_upload,
    process_document,
    sanitise_filename,
    stage_seed,
)

from .conftest import make_docx, make_pdf, make_txt


# ---------------------------------------------------------------------------
# Filename sanitisation -- the first line of defence against path traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\config.txt", "config.txt"),
        ("/absolute/path/report.pdf", "report.pdf"),
        ("C:\\Users\\me\\report.docx", "report.docx"),
        ("normal file (v2).txt", "normal file (v2).txt"),
    ],
)
def test_sanitise_filename_removes_directory_components(raw, expected):
    assert sanitise_filename(raw) == expected


def test_sanitise_filename_replaces_dangerous_characters():
    assert sanitise_filename("weird<>name|with:chars?.txt") == "weird_name_with_chars_.txt"


def test_sanitise_filename_handles_empty_and_dots():
    assert sanitise_filename("") == "document"
    assert sanitise_filename("...") == "document"


def test_sanitise_filename_truncates_long_names():
    name = sanitise_filename("a" * 400 + ".txt")
    assert len(name) <= 180
    assert name.endswith(".txt")


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


def test_check_upload_rejects_unsupported_extension(settings):
    with pytest.raises(UnsupportedFileError):
        check_upload("notes.exe", 10, settings)


def test_check_upload_rejects_missing_extension(settings):
    with pytest.raises(UnsupportedFileError):
        check_upload("Makefile", 10, settings)


def test_check_upload_rejects_empty_file(settings):
    with pytest.raises(ExtractionError):
        check_upload("notes.txt", 0, settings)


def test_check_upload_rejects_oversized_file(settings):
    settings.max_upload_mb = 1
    with pytest.raises(FileTooLargeError):
        check_upload("notes.txt", 2 * 1024 * 1024, settings)


def test_check_upload_accepts_supported_types(settings):
    assert check_upload("Notes.TXT", 10, settings) == ".txt"
    assert check_upload("paper.pdf", 10, settings) == ".pdf"
    assert check_upload("brief.docx", 10, settings) == ".docx"


# ---------------------------------------------------------------------------
# Stage bookkeeping
# ---------------------------------------------------------------------------


def test_stage_seed_covers_every_documented_stage():
    seed = stage_seed()
    assert [stage["name"] for stage in seed] == [stage["name"] for stage in STAGE_DEFINITIONS]
    assert len(seed) == 7
    assert all(stage["state"] == "pending" for stage in seed)


def test_compute_progress_weighting():
    assert compute_progress([]) == 0.0
    assert compute_progress([{"state": "pending"}] * 4) == 0.0
    assert compute_progress([{"state": "completed"}] * 5 + [{"state": "pending"}] * 5) == 0.5
    assert compute_progress([{"state": "running"}] + [{"state": "pending"}]) == 0.25
    assert compute_progress([{"state": "completed"}] * 3) == 1.0


# ---------------------------------------------------------------------------
# Full ingestion
# ---------------------------------------------------------------------------


def test_persist_upload_uses_generated_names_and_safe_paths(container):
    record = persist_upload(container, "../../evil.txt", b"hello", ".txt")
    stored = Path(record["stored_path"])
    assert stored.name == "source.txt", "the stored filename must not come from client input"
    assert stored.parent.parent == container.settings.upload_dir
    assert record["id"].startswith("doc_")
    assert stored.read_bytes() == b"hello"


def test_pipeline_indexes_a_txt_document(container):
    _name, data, _ct = make_txt()
    record = persist_upload(container, "helios.txt", data, ".txt")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())

    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "ready"
    assert row["indexed"] == 1
    assert row["chunk_count"] > 0
    assert row["char_count"] > 0
    assert container.vector_index.size == row["chunk_count"]

    stages = container.db.get_stages(record["id"])
    assert [stage["state"] for stage in stages] == ["completed"] * 7
    assert all(stage["detail"] for stage in stages), "every completed stage must explain what it did"


def test_pipeline_indexes_a_pdf_with_page_metadata(container):
    _name, data, _ct = make_pdf(
        pages=[
            "Page one describes the Wide Field Imager and its filter set.",
            "Page two describes the Low Frequency Spectrometer.",
        ]
    )
    record = persist_upload(container, "paper.pdf", data, ".pdf")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "ready"
    assert row["page_count"] == 2
    pages = {chunk["page"] for chunk in container.db.get_chunks(record["id"])}
    assert pages == {1, 2}, "page numbers must survive into chunk metadata for citations"


def test_pipeline_indexes_a_docx_document(container):
    _name, data, _ct = make_docx(paragraphs=["DOCX body text about calibration."])
    record = persist_upload(container, "brief.docx", data, ".docx")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "ready"
    assert container.db.chunk_count() > 0
    assert "calibration" in container.db.get_chunks(record["id"])[0]["text"]


def test_pipeline_marks_an_unreadable_file_failed_with_a_message(container):
    record = persist_upload(container, "broken.pdf", b"%PDF-1.4\ngarbage", ".pdf")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())

    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "failed"
    assert row["error"], "a failed document must explain why"
    assert row["indexed"] == 0
    failed_stage = next(stage for stage in container.db.get_stages(record["id"]) if stage["state"] == "failed")
    assert failed_stage["state"] == "failed"
    assert container.vector_index.size == 0


def test_pipeline_fails_when_the_stored_file_disappeared(container):
    record = persist_upload(container, "gone.txt", b"content", ".txt")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    Path(record["stored_path"]).unlink()

    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "failed"
    assert "could not be found" in row["error"].lower()


def test_reprocessing_the_same_document_does_not_duplicate_chunks(container):
    _name, data, _ct = make_txt()
    record = persist_upload(container, "helios.txt", data, ".txt")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    process_document(record["id"], container)
    first_count = container.db.chunk_count()

    # Retry path: remove existing rows, then run again.
    container.vector_index.remove_document(f"{record['id']}::")
    container.db.delete_document(record["id"])
    container.db.create_document({**record, "status": "queued", "chunk_count": 0, "indexed": False})
    container.db.reset_stages(record["id"], stage_seed())
    container.refresh()
    process_document(record["id"], container)

    assert container.db.chunk_count() == first_count
    assert container.vector_index.size == first_count


def test_pipeline_reports_stage_progress_truthfully(container, monkeypatch):
    """A stage must be 'running' while its work happens, never pre-completed."""
    observed: list[list[tuple[str, str]]] = []
    original = PipelineRunner._complete

    def spy(self, document_id, name, detail=""):
        result = original(self, document_id, name, detail)
        # Snapshot *after* the stage is written: what the API would report now.
        observed.append(
            [(row["name"], row["state"]) for row in self.container.db.get_stages(document_id)]
        )
        return result

    monkeypatch.setattr(PipelineRunner, "_complete", spy)

    _name, data, _ct = make_txt()
    record = persist_upload(container, "helios.txt", data, ".txt")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    process_document(record["id"], container)

    assert len(observed) == 7
    # When the first stage completes, nothing later may already be completed.
    assert observed[0][0] == ("validate", "completed")
    assert all(state != "completed" for _name, state in observed[0][1:])


def test_pipeline_warns_about_scanned_pdf_pages(container):
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    text = pdf.beginText(40, 780)
    text.textLine("Real text on page one.")
    pdf.drawText(text)
    pdf.showPage()
    pdf.rect(10, 10, 100, 100)  # page two has no text layer
    pdf.showPage()
    pdf.save()

    record = persist_upload(container, "mixed.pdf", buffer.getvalue(), ".pdf")
    container.db.create_document(record)
    container.db.reset_stages(record["id"], stage_seed())
    process_document(record["id"], container)

    row = container.db.get_document(record["id"])
    assert row["status"] == "ready"
    details = " ".join(stage["detail"] for stage in container.db.get_stages(record["id"]))
    assert "no extractable text" in details


def test_process_document_never_raises_for_unknown_document(container):
    # The worker is a daemon thread; it must not explode the process.
    process_document("doc_does_not_exist", container)
    assert container.db.list_documents() == []
