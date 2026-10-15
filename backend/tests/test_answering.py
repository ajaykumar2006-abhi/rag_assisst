"""Regression tests for excerpt selection and extractive answer assembly.

Both behaviours were fixed after they produced wrong *user-visible* output, so
they are pinned here:

* a citation excerpt must contain the sentence it was cited for, in full;
* an extractive answer must not pad itself out with sentences that share a single
  word with the question, and must not repeat a sentence it already used.
"""

from __future__ import annotations

from app.services.answering import ExtractiveAnswerer
from app.services.qa import build_excerpt, to_citations
from app.services.retrieval import RetrievedChunk
from app.services.text_utils import split_sentences

QUESTION = "How long is the proprietary period before public data release?"
ANSWER_SENTENCE = (
    "Data products are released to the public archive after a proprietary period of twelve months."
)
FILLER = "The ground segment reviews the antenna schedule during the weekly coordination meeting."


def make_chunk(text: str, index: int = 1, fused: float = 0.4) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"doc::000{index}",
        document_id="doc",
        document_filename="report.pdf",
        page=index,
        text=text,
        dense_score=0.4,
        lexical_score=0.3,
        fused_score=fused,
    )


# ---------------------------------------------------------------------------
# build_excerpt
# ---------------------------------------------------------------------------


def test_short_text_is_returned_unchanged():
    assert build_excerpt(ANSWER_SENTENCE, QUESTION, limit=1000) == ANSWER_SENTENCE


def test_excerpt_contains_the_anchor_sentence_when_it_sits_at_the_end():
    text = " ".join([FILLER] * 6 + [ANSWER_SENTENCE])
    excerpt = build_excerpt(text, QUESTION, limit=220)
    assert ANSWER_SENTENCE in excerpt


def test_excerpt_contains_the_anchor_sentence_when_it_sits_in_the_middle():
    text = " ".join([FILLER] * 6 + [ANSWER_SENTENCE] + [FILLER] * 6)
    excerpt = build_excerpt(text, QUESTION, limit=220)
    assert ANSWER_SENTENCE in excerpt


def test_excerpt_is_marked_as_truncated_on_the_side_it_was_cut():
    text = " ".join([FILLER] * 6 + [ANSWER_SENTENCE] + [FILLER] * 6)
    excerpt = build_excerpt(text, QUESTION, limit=220)
    assert excerpt.startswith("...")
    assert excerpt.endswith("...")


def test_excerpt_never_exceeds_the_limit():
    text = " ".join([FILLER] * 20 + [ANSWER_SENTENCE])
    for limit in (120, 200, 320, 420):
        assert len(build_excerpt(text, QUESTION, limit=limit)) <= limit


def test_anchor_longer_than_the_limit_is_still_shown():
    excerpt = build_excerpt(ANSWER_SENTENCE, QUESTION, limit=40)
    assert excerpt.startswith("Data products are released")
    assert len(excerpt) <= 40


# ---------------------------------------------------------------------------
# Extractive answerer
# ---------------------------------------------------------------------------


def test_weakly_related_sentences_are_excluded_from_the_answer():
    text = (
        f"{ANSWER_SENTENCE} "
        "The primary control centre is at Svalbard with a data downlink station on Ascension Island."
    )
    draft = ExtractiveAnswerer().answer(QUESTION, [make_chunk(text)], max_sentences=6)

    assert "twelve months" in draft.text
    assert "Svalbard" not in draft.text
    assert draft.used_citations == {1}


def test_duplicate_sentences_across_chunks_are_reported_once():
    chunks = [make_chunk(ANSWER_SENTENCE, index=1), make_chunk(ANSWER_SENTENCE, index=2)]
    draft = ExtractiveAnswerer().answer(QUESTION, chunks, max_sentences=6)

    assert draft.text.lower().count("proprietary period of twelve months") == 1
    # The duplicate must not claim a citation it did not contribute.
    assert draft.used_citations == {1}


def test_strongest_sentence_comes_first_and_every_sentence_is_verbatim():
    text = (
        f"{FILLER} {ANSWER_SENTENCE} The recorder holds 48 hours of survey data before downlink."
    )
    draft = ExtractiveAnswerer().answer(QUESTION, [make_chunk(text)], max_sentences=3)

    assert draft.text.startswith("Data products are released")
    # Remove the citation markers, re-split, and confirm every returned sentence is
    # copied character-for-character out of the source passage.
    # The service writes "sentence [n]." — keep the terminating period when the
    # marker is stripped so the text can be re-split into sentences.
    plain = draft.text.replace(" [1].", ".").replace("[1]", "")
    sentences = [sentence.strip() for sentence in split_sentences(plain) if sentence.strip()]
    assert sentences, "the answer should contain at least one sentence"
    for sentence in sentences:
        assert sentence in text, f"not verbatim: {sentence!r}"


def test_answer_with_no_overlapping_sentence_is_declined():
    text = "The antenna schedule is reviewed weekly by the ground segment coordination group."
    draft = ExtractiveAnswerer().answer(QUESTION, [make_chunk(text)], max_sentences=3)

    assert draft.mode.value == "insufficient"
    assert draft.used_citations == set()


def test_no_chunks_is_declined_without_inventing_an_answer():
    draft = ExtractiveAnswerer().answer(QUESTION, [], max_sentences=3)
    assert draft.mode.value == "insufficient"
    assert "could not find" in draft.text.lower()


def test_draft_records_the_sentences_used_for_each_citation():
    chunks = [make_chunk(f"{FILLER} {ANSWER_SENTENCE}", index=1)]
    draft = ExtractiveAnswerer().answer(QUESTION, chunks, max_sentences=3)

    assert 1 in draft.used_sentences
    assert ANSWER_SENTENCE in draft.used_sentences[1]


# ---------------------------------------------------------------------------
# End to end: what the user sees when they follow a citation
# ---------------------------------------------------------------------------


def test_citation_indexes_match_the_markers_used_in_the_answer():
    """Citation [3] must be the third retrieved chunk, even if [2] was not used.

    Re-numbering the returned citations makes every marker after a skipped chunk
    point at the wrong source, which is worse than no citation at all.
    """
    chunks = [make_chunk(f"Chunk number {index} text. {ANSWER_SENTENCE}", index=index) for index in (1, 2, 3)]
    citations = to_citations(chunks, QUESTION, used={1, 3})

    assert [citation.index for citation in citations] == [1, 3]
    assert citations[1].chunk_id == "doc::0003"


def test_cited_excerpt_contains_the_sentence_the_answer_quoted(client, ingest):
    """A citation must show the passage the answer relied on, not just any window.

    The document is deliberately built so the highest-scoring sentence and the
    answering sentence differ: the opening sentence shares "wide" and "field" with
    the question while the answer sentence shares "detector" and "cooled".
    """
    text = (
        "HELIOS DEEP FIELD SURVEY - INSTRUMENT SPECIFICATIONS\n\n"
        "The Wide Field Imager is a 1.2 metre aperture telescope feeding a 96 megapixel "
        "focal plane array. Its field of view is 3.4 square degrees, split across four "
        "detector banks. The detector is cooled to 118 kelvin by a single stage radiator "
        "and the focal plane is held stable to within 0.02 kelvin.\n"
    )
    question = "What temperature is the wide field detector cooled to?"
    quoted = (
        "The detector is cooled to 118 kelvin by a single stage radiator and the focal "
        "plane is held stable to within 0.02 kelvin."
    )

    document_id, _detail = ingest(("specs.txt", text.encode(), "text/plain"))
    body = client.post(
        f"/api/v1/documents/{document_id}/questions", json={"question": question}
    ).json()

    assert body["answer_mode"] == "extractive", body
    # The marker is inserted before the closing period, so compare without it.
    assert quoted.rstrip(".") in body["answer"], body["answer"]
    assert body["citations"], "an extractive answer must carry its citations"
    assert any(quoted in citation["excerpt"] for citation in body["citations"]), (
        "no citation excerpt contained the quoted sentence: "
        + repr([citation["excerpt"][:120] for citation in body["citations"]])
    )
