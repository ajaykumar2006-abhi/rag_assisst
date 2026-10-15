"""Hybrid retrieval tests against a real container with real indexed chunks."""

from __future__ import annotations

from app.services.chunking import chunk_sections
from app.services.extraction import ExtractedSection

DOC_USAGE = (
    "The Low Frequency Spectrometer covers 40 to 320 megahertz with a spectral "
    "resolution of 3.2 kilohertz per channel.\n\n"
    "The Wide Field Imager reaches a limiting magnitude of 26.1 in a 900 second exposure.\n\n"
    "The observatory operates at an altitude of 612 kilometres.\n"
)
DOC_OPS = (
    "Safe mode entry occurs automatically when the guidance solution is invalid for more "
    "than 90 seconds.\n\n"
    "Calibration is performed every 30 days using a noise reference lamp.\n"
)


def _index_text(container, document_id: str, filename: str, text: str) -> None:
    container.db.create_document(
        {
            "id": document_id,
            "filename": filename,
            "stored_path": str(container.settings.upload_dir / f"{document_id}.txt"),
            "extension": ".txt",
            "size_bytes": len(text),
            "sha256": "0" * 64,
            "status": "ready",
            "embedding_provider": container.embedder.name,
            "embedding_dim": container.embedder.dim,
            "answer_provider": container.answerer.name,
            "indexed": True,
        }
    )
    chunks = chunk_sections(
        [ExtractedSection(page=None, text=text)],
        document_id,
        chunk_size=container.settings.chunk_size,
        chunk_overlap=container.settings.chunk_overlap,
        max_chunks=200,
    )
    container.store_chunks(chunks)


def test_search_finds_the_chunk_containing_the_answer(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    results = container.search("What frequency range does the spectrometer cover?")
    assert results, "retrieval returned nothing for a question with an in-corpus answer"
    assert "megahertz" in results[0].text
    assert results[0].fused_score > 0


def test_search_reports_component_scores(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    top = container.search("limiting magnitude in a 900 second exposure")[0]
    assert 0.0 <= top.dense_score <= 1.0
    assert 0.0 <= top.lexical_score <= 1.0
    assert top.fused_score > 0
    assert top.chunk_id.startswith("doc_usage::")


def test_search_respects_top_k(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    _index_text(container, "doc_ops", "ops.txt", DOC_OPS)
    assert len(container.search("calibration and spectrometer", top_k=2)) <= 2
    assert len(container.search("calibration and spectrometer", top_k=50)) >= 2


def test_search_can_be_scoped_to_one_document(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    _index_text(container, "doc_ops", "ops.txt", DOC_OPS)
    results = container.search("calibration", document_ids=["doc_ops"])
    assert results
    assert {chunk.document_id for chunk in results} == {"doc_ops"}


def test_search_on_unrelated_question_scores_low(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    relevant = container.search("spectrometer megahertz")[0].fused_score
    unrelated = container.search("zebra migration patterns in the Serengeti")[0].fused_score
    assert unrelated < relevant


def test_search_with_no_indexed_documents_returns_nothing(container):
    assert container.search("anything at all") == []


def test_search_with_empty_query_returns_nothing(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    assert container.search("   ") == []


def test_lexical_only_mode_still_ranks_by_term_overlap(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    container.settings.dense_weight = 0.0
    container.settings.lexical_weight = 1.0
    try:
        results = container.search("kilohertz per channel")
        assert results
        assert "kilohertz" in results[0].text
    finally:
        container.settings.dense_weight = 0.65
        container.settings.lexical_weight = 0.35


def test_removing_a_document_removes_it_from_retrieval(container):
    _index_text(container, "doc_usage", "usage.txt", DOC_USAGE)
    assert container.search("megahertz")
    from pathlib import Path

    container.remove_document("doc_usage", Path(container.settings.upload_dir / "doc_usage.txt"))
    assert container.search("megahertz") == []
    assert container.vector_index.size == 0
    assert container.db.chunk_count() == 0
