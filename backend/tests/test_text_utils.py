"""Tests for the shared text helpers."""

from __future__ import annotations

from app.services.text_utils import (
    content_tokens,
    estimate_tokens,
    extract_keywords,
    join_phrases,
    keyword_overlap,
    split_sentences,
    tokenize,
    truncate,
)


def test_tokenize_lowercases_and_keeps_internal_punctuation():
    assert tokenize("Don't STOP the 3rd-wave test.") == ["don't", "stop", "the", "3rd-wave", "test"]


def test_content_tokens_removes_stopwords():
    assert content_tokens("what is the altitude of the orbit") == ["altitude", "orbit"]


def test_keyword_overlap_is_a_fraction():
    assert keyword_overlap(["altitude", "orbit"], "the altitude of the orbit is 612 km") == 1.0
    assert keyword_overlap(["altitude", "spectrometer"], "the altitude is 612 km") == 0.5
    assert keyword_overlap([], "anything") == 0.0


def test_split_sentences_keeps_abbreviations_together():
    sentences = split_sentences("Dr. Vance led the review board. The board approved it.")
    assert len(sentences) == 2
    assert sentences[0].startswith("Dr. Vance")


def test_split_sentences_handles_empty_input():
    assert split_sentences("") == []


def test_extract_keywords_ranks_by_frequency():
    keywords = extract_keywords("orbit survey orbit survey orbit calibration", limit=2)
    assert keywords == ["orbit", "survey"]


def test_truncate_does_not_cut_mid_word():
    result = truncate("alpha bravo charlie delta", 20)
    assert result.endswith("...")
    assert "charli..." not in result
    assert len(result) <= 23


def test_truncate_returns_short_text_unchanged():
    assert truncate("short", 50) == "short"


def test_estimate_tokens_is_at_least_one():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcdefgh") == 2


def test_join_phrases():
    assert join_phrases([]) == ""
    assert join_phrases(["a"]) == "a"
    assert join_phrases(["a", "b", "c"]) == "a, b and c"
