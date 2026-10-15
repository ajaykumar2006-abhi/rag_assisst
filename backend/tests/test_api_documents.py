"""API integration tests: health, upload, status, listing, sources, deletion."""

from __future__ import annotations

import time

from .conftest import make_docx, make_pdf, make_txt


def test_health_reports_real_configuration(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["embedding_provider"] == "hashing-subword-v1"
    assert body["embedding_dim"] > 0
    assert body["answer_provider"] == "extractive"
    # The default local extractive path must not be advertised as generative.
    assert body["generative_available"] is False
    assert body["documents_indexed"] == 0
    assert body["data_dir"]


def test_openapi_document_is_served(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "RAG Document Intelligence API"
    for path in (
        "/api/v1/health",
        "/api/v1/documents",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/status",
        "/api/v1/documents/{document_id}/sources",
        "/api/v1/documents/{document_id}/questions",
        "/api/v1/evaluation/summary",
        "/api/v1/evaluation/run",
        "/api/v1/settings",
    ):
        assert path in schema["paths"], f"{path} is missing from the published contract"


def test_upload_then_status_reaches_ready(client, upload, wait_for_ready):
    response = upload(client, make_txt())
    assert response.status_code == 201
    body = response.json()
    assert body["message"]
    document = body["document"]
    assert document["status"] in ("queued", "processing", "ready")
    assert document["filename"] == "helios.txt"
    assert document["extension"] == ".txt"

    status = wait_for_ready(document["id"])
    assert status["status"] == "ready"
    assert status["indexed"] is True
    assert status["progress"] == 1.0
    assert status["retryable"] is False
    assert len(status["stages"]) == 7


def test_upload_pdf_and_docx_are_indexed(client, ingest):
    pdf_id, pdf_detail = ingest(make_pdf())
    assert pdf_detail["status"] == "ready"
    assert pdf_detail["page_count"] == 2
    assert pdf_detail["chunk_count"] > 0

    docx_id, docx_detail = ingest(make_docx())
    assert docx_detail["status"] == "ready"
    assert docx_detail["chunk_count"] > 0


def test_document_list_reflects_uploads(client, ingest):
    assert client.get("/api/v1/documents").json() == []
    document_id, _detail = ingest(make_txt())
    listing = client.get("/api/v1/documents").json()
    assert len(listing) == 1
    assert listing[0]["id"] == document_id
    assert listing[0]["status"] == "ready"


def test_sources_endpoint_returns_indexed_chunks(client, ingest):
    document_id, detail = ingest(make_txt())
    response = client.get(f"/api/v1/documents/{document_id}/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["filename"] == "helios.txt"
    assert len(body["sources"]) == detail["chunk_count"]
    first = body["sources"][0]
    assert first["index"] == 1
    assert first["chunk_id"].startswith(f"{document_id}::")
    assert first["excerpt"]


def test_upload_rejects_unsupported_extension(client, upload):
    response = upload(client, ("payload.exe", b"MZ\x90\x00", "application/octet-stream"))
    assert response.status_code == 415
    error = response.json()["error"]
    assert error["code"] == "unsupported_file"
    assert ".exe" in error["message"]


def test_upload_rejects_content_that_contradicts_its_extension(client, upload):
    response = upload(client, ("notes.pdf", b"this is definitely not a pdf", "application/pdf"))
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file"


def test_upload_rejects_empty_file(client, upload, container):
    response = upload(client, ("empty.txt", b"", "text/plain"))
    assert response.status_code == 422
    assert "empty" in response.json()["error"]["message"].lower()
    # Nothing may be left behind by a rejected upload.
    assert list(container.settings.upload_dir.iterdir()) == []


def test_upload_rejects_oversized_file(client, upload, container):
    container.settings.max_upload_mb = 1
    response = upload(client, ("big.txt", b"x" * (2 * 1024 * 1024), "text/plain"))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_upload_without_a_file_returns_validation_error(client):
    response = client.post("/api/v1/documents")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_document_returns_not_found(client):
    for path in (
        "/api/v1/documents/doc_missing",
        "/api/v1/documents/doc_missing/status",
        "/api/v1/documents/doc_missing/sources",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"


def test_delete_removes_document_file_vectors_and_rows(client, ingest, container):
    document_id, _detail = ingest(make_txt())
    stored = list(container.settings.upload_dir.rglob("source.txt"))
    assert stored, "the upload should exist on disk before deletion"
    assert container.vector_index.size > 0

    response = client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == document_id
    assert body["vectors_removed"] > 0
    assert body["files_removed"] == 1
    assert body["index_size_after"] == 0

    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.get("/api/v1/documents").json() == []
    assert container.db.chunk_count() == 0
    assert not list(container.settings.upload_dir.rglob("source.txt"))


def test_delete_is_idempotent_in_effect(client, ingest):
    document_id, _detail = ingest(make_txt())
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 200
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 404


def test_retry_reprocesses_a_ready_document(client, ingest, container):
    document_id, detail = ingest(make_txt())
    original_chunks = detail["chunk_count"]

    response = client.post(f"/api/v1/documents/{document_id}/retry")
    assert response.status_code == 202

    deadline = time.time() + 30
    status = {}
    while time.time() < deadline:
        status = client.get(f"/api/v1/documents/{document_id}/status").json()
        if status["status"] in ("ready", "failed"):
            break
        time.sleep(0.1)

    assert status["status"] == "ready"
    assert container.db.chunk_count() == original_chunks
    assert container.vector_index.size == original_chunks


def test_retry_unknown_document_returns_not_found(client):
    assert client.post("/api/v1/documents/doc_missing/retry").status_code == 404


def test_index_survives_a_container_restart(client, ingest, settings):
    """Chunks and vectors must be recoverable from disk after a restart."""
    document_id, detail = ingest(make_txt())
    assert detail["chunk_count"] > 0

    from app.services.container import ServiceContainer

    fresh = ServiceContainer(settings)
    try:
        assert fresh.db.chunk_count() == detail["chunk_count"]
        assert fresh.vector_index.size == detail["chunk_count"]
        assert fresh.rebuild_reason in ("loaded from disk", "index out of sync with stored chunks")
        results = fresh.search("Cryo-Spectrometer Array")
        assert results, "retrieval must work immediately after a restart"
    finally:
        fresh.shutdown()


def test_vectors_are_rebuilt_when_the_index_files_are_deleted(client, ingest, settings):
    document_id, detail = ingest(make_txt())
    for path in (settings.index_dir / "collection").glob("*"):
        path.unlink()

    from app.services.container import ServiceContainer

    fresh = ServiceContainer(settings)
    try:
        assert fresh.vector_index.size == detail["chunk_count"], "missing index files must trigger a rebuild"
        assert fresh.search("Tycho Institute")
    finally:
        fresh.shutdown()
