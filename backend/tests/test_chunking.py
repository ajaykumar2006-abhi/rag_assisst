"""Chunking tests: boundaries, overlap, metadata preservation and limits."""

from __future__ import annotations

import pytest

from app.services.chunking import chunk_sections, make_chunk_id, pages_covered
from app.services.extraction import ExtractedSection


def test_short_document_becomes_one_chunk():
    sections = [ExtractedSection(page=1, text="A short sentence about the survey.")]
    chunks = chunk_sections(sections, "doc_1", chunk_size=400, chunk_overlap=50, max_chunks=10)
    assert len(chunks) == 1
    assert chunks[0].text == "A short sentence about the survey."
    assert chunks[0].page == 1
    assert chunks[0].id == make_chunk_id("doc_1", 0)


def test_long_document_is_split_and_never_loses_text():
    words = " ".join(f"token{index}" for index in range(600))
    sections = [ExtractedSection(page=None, text=words)]
    chunks = chunk_sections(sections, "doc_2", chunk_size=300, chunk_overlap=40, max_chunks=100)
    assert len(chunks) > 1

    # Every token must appear somewhere: nothing silently dropped.
    joined = " ".join(chunk.text for chunk in chunks)
    for index in (0, 150, 320, 599):
        assert f"token{index}" in joined


def test_overlap_produces_shared_context_between_neighbours():
    paragraphs = "\n\n".join(f"Paragraph {index} " + ("filler " * 40) for index in range(6))
    sections = [ExtractedSection(page=None, text=paragraphs)]
    chunks = chunk_sections(sections, "doc_3", chunk_size=300, chunk_overlap=120, max_chunks=50)
    assert len(chunks) >= 2
    for previous, current in zip(chunks, chunks[1:]):
        assert current.char_start < previous.char_end, "consecutive chunks are not overlapping"


def test_metadata_is_preserved_across_pages():
    sections = [
        ExtractedSection(page=1, text="Page one text " * 30),
        ExtractedSection(page=2, text="Page two text " * 30),
    ]
    chunks = chunk_sections(sections, "doc_4", chunk_size=200, chunk_overlap=20, max_chunks=100)
    assert {chunk.page for chunk in chunks} == {1, 2}
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.document_id == "doc_4" for chunk in chunks)
    assert all(chunk.id.startswith("doc_4::") for chunk in chunks)
    assert pages_covered(chunks) == 2


def test_character_offsets_are_monotonic():
    sections = [ExtractedSection(page=None, text="abcdefghij " * 60)]
    chunks = chunk_sections(sections, "doc_5", chunk_size=120, chunk_overlap=10, max_chunks=100)
    previous_end = -1
    for chunk in chunks:
        assert chunk.char_start >= 0
        assert chunk.char_end > chunk.char_start
        assert chunk.char_start >= previous_end - 10  # allows declared overlap
        previous_end = chunk.char_end


def test_empty_pages_are_skipped_but_offsets_stay_continuous():
    sections = [
        ExtractedSection(page=1, text="Real content here."),
        ExtractedSection(page=2, text=""),
        ExtractedSection(page=3, text="More content on page three."),
    ]
    chunks = chunk_sections(sections, "doc_6", chunk_size=400, chunk_overlap=20, max_chunks=10)
    assert [chunk.page for chunk in chunks] == [1, 3]
    assert chunks[1].char_start > chunks[0].char_end


def test_whitespace_only_sections_produce_no_chunks():
    sections = [ExtractedSection(page=1, text="   \n\n  ")]
    assert chunk_sections(sections, "doc_7", chunk_size=100, chunk_overlap=10, max_chunks=10) == []


def test_max_chunks_limit_is_respected():
    sections = [ExtractedSection(page=None, text="word " * 5000)]
    chunks = chunk_sections(sections, "doc_8", chunk_size=100, chunk_overlap=10, max_chunks=7)
    assert len(chunks) == 7


def test_invalid_parameters_raise():
    sections = [ExtractedSection(page=None, text="text")]
    with pytest.raises(ValueError):
        chunk_sections(sections, "doc_9", chunk_size=0, chunk_overlap=0, max_chunks=10)
    with pytest.raises(ValueError):
        chunk_sections(sections, "doc_9", chunk_size=100, chunk_overlap=100, max_chunks=10)
    with pytest.raises(ValueError):
        chunk_sections(sections, "doc_9", chunk_size=100, chunk_overlap=-5, max_chunks=10)


def test_chunks_prefer_sentence_boundaries():
    text = "First sentence is here. Second sentence follows. " * 12
    chunks = chunk_sections(
        [ExtractedSection(page=None, text=text)], "doc_10", chunk_size=200, chunk_overlap=0, max_chunks=50
    )
    assert len(chunks) > 1
    # A sentence-aware split should not leave a dangling mid-word fragment.
    for chunk in chunks[:-1]:
        assert chunk.text.rstrip().endswith((".", "!", "?")), chunk.text[-40:]
