"""Question answering orchestration.

Ties together retrieval, the answer provider, citation construction and
conversation persistence. Two behaviours matter for trustworthiness:

* **Evidence gate** -- if the best fused score is below ``min_relevance``, or the
  best passage has neither keyword overlap nor meaningful vector similarity, we
  say so instead of answering. A confident-sounding answer with no supporting
  passage is worse than an honest "not in these documents".* **Citation integrity** -- citation markers map 1:1 onto retrieved chunks and
  carry the exact document id, page and character offsets, so the UI can show the
  real source. Scores are never presented as probabilities of correctness.
* **Conversation context** -- a follow-up whose own words fail the evidence gate
  is retried once with the previous user questions added to the query, because
  "and its launch date?" shares no vocabulary with the document on its own. The
  gate still decides, and the extractive answerer still selects sentences against
  the *current* question only, so history can widen retrieval but can never
  manufacture support for a question the documents do not cover.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Dict, List, Optional, Sequence, Set

from ..schemas.models import AnswerMode, AnswerResponse, Citation
from ..storage.db import utcnow
from .container import ServiceContainer
from .retrieval import RetrievedChunk
from .text_utils import content_tokens, split_sentences, tokenize, truncate

logger = logging.getLogger(__name__)

# Character budget for a citation excerpt. It is deliberately wide enough to hold a
# whole multi-sentence extractive answer drawn from one chunk (the default answer
# length is 6 sentences): if the budget were tighter, an answer's own sentences
# would be crowded out of the passage shown beside its citation and the citation
# could not be checked against the answer.
EXCERPT_CHARS = 700

# --- Evidence-support thresholds --------------------------------------------
# A candidate passage counts as "supported" when it has real keyword overlap OR a
# dense similarity clearly above the noise floor. Both constants were calibrated
# against the positive/negative probes documented in
# ``ServiceQA._evidence_insufficient`` and must be re-measured if the embedder or
# the fusion weights change.
SUPPORT_DENSE_FLOOR = 0.12
SUPPORT_LEXICAL_FLOOR = 0.30

# Bound for the context-expanded retrieval query: the current question plus at
# most CONTEXT_TURNS earlier user questions, each capped so one rambling turn
# cannot push the query past what BM25 can meaningfully score.
CONTEXT_TURNS = 2
CONTEXT_TURN_CHARS = 400
CONTEXT_QUERY_CHARS = 1200


def build_excerpt(
    text: str,
    question: str,
    limit: int = EXCERPT_CHARS,
    prefer: Optional[Sequence[str]] = None,
) -> str:
    """Return the most question-relevant window of ``text``.

    The window is anchored on the sentence that best matches the question, or on the
    first ``prefer`` sentence that the answer actually quoted, and it is guaranteed
    to contain that anchor in full. That guarantee is the point: a reader who
    follows a citation must see the sentence the answer used, otherwise the
    citation cannot be checked.

    The window grows right first, then left, and only accepts a neighbour when it
    fits the remaining budget — so no truncation is ever needed and the anchor can
    never be cut off at the end.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text

    tokens = content_tokens(question)
    sentences = split_sentences(text) or [text]

    # Weight each question term by how rare it is *in this document*, mirroring the
    # IDF idea the BM25 side of retrieval already uses. Without this, a common word
    # in the document ("field") counts as much as a distinctive one ("cooled"), and
    # the excerpt centres on the wrong sentence whenever the two tie.
    token_set = set(tokens)
    sentence_tokens = [set(tokenize(sentence)) for sentence in sentences]
    weights = {
        token: math.log(1.0 + len(sentences) / (1.0 + sum(1 for st in sentence_tokens if token in st)))
        for token in token_set
    }
    total_weight = sum(weights.values())

    def relevance(index: int) -> float:
        if total_weight <= 0:
            return 0.0
        present = sum(weight for token, weight in weights.items() if token in sentence_tokens[index])
        return present / total_weight

    best_index, best_score = 0, -1.0
    for index in range(len(sentences)):
        score = relevance(index)
        if score > best_score:
            best_index, best_score = index, score

    # Sentences the answer actually quoted win over the highest-scoring one, because
    # showing the evidence that was used is what makes a citation checkable. When
    # several were quoted from this chunk they are shown together if they fit.
    normalized_sentences = [" ".join(candidate.lower().split()) for candidate in sentences]
    quoted_indices: List[int] = []
    for quoted in prefer or []:
        fingerprint = " ".join(quoted.lower().split()).rstrip(".")
        if not fingerprint:
            continue
        for index, normalized in enumerate(normalized_sentences):
            if fingerprint in normalized and index not in quoted_indices:
                quoted_indices.append(index)
                break

    if quoted_indices:
        start, end = min(quoted_indices), max(quoted_indices)
        length = len(" ".join(sentences[start : end + 1]))
        if length > limit:
            # The quoted run does not fit: keep the quoted sentence that overlaps the
            # question most, breaking ties towards the longer (more informative) one.
            best_index = max(
                (relevance(index), len(sentences[index]), index) for index in quoted_indices
            )[2]
            start = end = best_index
            length = len(sentences[best_index])
    else:
        start = end = best_index
        length = len(sentences[best_index])

    if start == end and len(sentences[start]) > limit:
        # The anchor alone does not fit: return it truncated rather than losing it.
        return sentences[start][: max(1, limit - 3)].rstrip() + "..."
    while True:
        grew = False
        if end < len(sentences) - 1 and length + len(sentences[end + 1]) + 1 <= limit:
            end += 1
            length += len(sentences[end]) + 1
            grew = True
        if start > 0 and length + len(sentences[start - 1]) + 1 <= limit:
            start -= 1
            length += len(sentences[start]) + 1
            grew = True
        if not grew:
            break

    window = " ".join(sentences[start : end + 1]).strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(sentences) - 1 else ""
    return f"{prefix}{window}{suffix}".strip()


def to_citations(
    chunks: Sequence[RetrievedChunk],
    question: str,
    used: Optional[Set[int]] = None,
    used_sentences: Optional[Dict[int, List[str]]] = None,
) -> List[Citation]:
    """Convert retrieved chunks into citation records.

    ``used`` restricts the output to the markers the answer actually referenced;
    when it is ``None`` every retrieved chunk becomes a citation.

    ``used_sentences`` maps a citation marker to the sentences quoted from that
    chunk; the excerpt is anchored on those sentences so the passage shown beside a
    citation is the passage the answer relied on.
    """
    citations: List[Citation] = []
    for index, chunk in enumerate(chunks, start=1):
        if used is not None and index not in used:
            continue
        citations.append(
            Citation(
                # The marker used in the answer text, *not* a re-numbered position:
                # if the answer skips a chunk, citation [3] must still be the third
                # retrieved chunk that the reader is being sent to.
                index=index,
                document_id=chunk.document_id,
                filename=chunk.document_filename,
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                score=round(chunk.fused_score, 6),
                dense_score=round(chunk.dense_score, 6),
                lexical_score=round(chunk.lexical_score, 6),
                excerpt=build_excerpt(
                    chunk.text,
                    question,
                    prefer=None if used_sentences is None else used_sentences.get(index),
                ),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
        )
    return citations


class QAService:
    """Answers questions against one or more indexed documents."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.settings = container.settings

    def _resolve_documents(self, document_ids: Optional[Sequence[str]]) -> List[Dict]:
        """Return metadata for the documents in scope, rejecting unusable ones."""
        if not document_ids:
            ready = [
                dict(row)
                for row in self.container.db.list_documents()
                if row["status"] == "ready" and row["indexed"]
            ]
            return ready

        resolved: List[Dict] = []
        missing: List[str] = []
        not_ready: List[str] = []
        for document_id in document_ids:
            row = self.container.db.get_document(document_id)
            if row is None:
                missing.append(document_id)
            elif row["status"] != "ready" or not row["indexed"]:
                not_ready.append(document_id)
            else:
                resolved.append(dict(row))

        if missing:
            from ..core.errors import NotFoundError

            raise NotFoundError(f"Unknown document id(s): {', '.join(missing)}")
        if not_ready and not resolved:
            from ..core.errors import ConflictError

            raise ConflictError(
                "The selected document is still being processed. Wait until indexing completes."
            )
        return resolved

    def _evidence_insufficient(self, retrieved: Sequence) -> tuple[bool, str]:
        """Decide whether the retrieved evidence can support an answer at all.

        Two independent signals must fail before we refuse, because either one
        alone produces bad behaviour:

        1. the tunable fused-score floor (``MIN_RELEVANCE``), and
        2. a *support* rule on the two component scores.

        Why a second rule is needed -- every number below was produced by
        ``scripts/measure_evidence_gate.py`` against the shipped fixtures with the
        default hashing embedder (dense=0.65 / lexical=0.35, min_relevance=0.05):

        ======================================================  =====  =====  =======
        probe                                                   fused  dense  lexical
        ======================================================  =====  =====  =======
        "When did the Helios mission launch?" (answered)        0.255  0.186    0.383
        "How big is the main telescope mirror?" (answered)      0.161  0.145    0.191
        "What is the nominal duration of a downlink pass?"       0.346  0.264    0.498
        "Which football team won the 1994 FIFA World Cup..."      0.151  0.094    0.256  REFUSED
        "How do I bake sourdough bread at home?"                0.054  0.082    0.000  REFUSED
        "What is the capital of Mongolia?"                      0.081  0.090    0.000  REFUSED
        ======================================================  =====  =====  =======

        A single global floor cannot separate these: on a one-document corpus a
        genuinely answerable question ("What transmitter and data rate does the
        downlink use?") scored only 0.127 fused, so a floor high enough to reject the
        unrelated questions above would refuse real answers. The component scores do
        separate them -- every genuine question has either real keyword overlap or a
        dense score clearly above the noise band, while none of the unrelated probes
        has both.
        """
        if not retrieved:
            return True, "No passage in these documents was retrievable at all."

        top = retrieved[0]
        best = top.fused_score

        if best < self.settings.min_relevance:
            return True, (
                f"The best match scored {best:.3f}, below the configured relevance "
                f"threshold of {self.settings.min_relevance:.2f}."
            )

        if top.dense_score < SUPPORT_DENSE_FLOOR and top.lexical_score < SUPPORT_LEXICAL_FLOOR:
            return True, (
                "The closest passage shares almost no wording with the question "
                f"(vector similarity {top.dense_score:.3f}, keyword overlap "
                f"{top.lexical_score:.3f}), which is the signature of a question this "
                "document set does not cover."
            )

        return False, ""

    def _prior_questions(self, conversation_id: str) -> List[str]:
        """The most recent user questions in this conversation, bounded.

        Only questions are reused. Assistant answers are verbatim document text
        and would drag arbitrary chunk vocabulary into the query, which could
        pull in passages for reasons unrelated to what the user actually asked.
        """
        try:
            rows = self.container.db.get_messages(conversation_id)
        except Exception as exc:  # noqa: BLE001 - context is an enhancement, never a failure path
            logger.warning("Could not read conversation %s for context: %s", conversation_id, exc)
            return []
        questions: List[str] = []
        for row in rows:
            if row["role"] != "user":
                continue
            text = str(row["content"] or "").strip()
            if text:
                questions.append(truncate(text, CONTEXT_TURN_CHARS))
        return questions[-CONTEXT_TURNS:]

    def answer(
        self,
        question: str,
        document_ids: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
        conversation_id: Optional[str] = None,
    ) -> AnswerResponse:
        started = time.perf_counter()
        documents = self._resolve_documents(document_ids)

        if not documents:
            return AnswerResponse(
                question=question,
                answer=(
                    "There are no indexed documents yet. Upload a PDF, TXT or DOCX file "
                    "in the workspace and I will be able to answer questions about it."
                ),
                answer_mode=AnswerMode.INSUFFICIENT,
                insufficient_evidence=True,
                notice="No documents are indexed.",
                embedding_provider=self.container.embedder.name,
            )

        scope_ids = [document["id"] for document in documents]
        k = top_k or self.settings.top_k
        retrieved = self.container.search(question, top_k=k, document_ids=scope_ids)

        best = retrieved[0].fused_score if retrieved else 0.0
        insufficient, reason = self._evidence_insufficient(retrieved)
        if insufficient and conversation_id:
            # Retry once with earlier turns of *this* conversation added to the
            # query. The same gate judges the expanded retrieval, and because the
            # answerer still scores sentences against the current question alone,
            # an out-of-scope follow-up stays refused even when the context makes
            # the expanded retrieval look strong.
            context = self._prior_questions(conversation_id)
            if context:
                expanded_query = truncate(" ".join([question, *context]), CONTEXT_QUERY_CHARS)
                expanded = self.container.search(expanded_query, top_k=k, document_ids=scope_ids)
                expanded_insufficient, expanded_reason = self._evidence_insufficient(expanded)
                if not expanded_insufficient:
                    retrieved = expanded
                    insufficient = False
                    reason = expanded_reason
                    logger.info(
                        "Conversation context widened retrieval for question %r.", question[:80]
                    )
        if insufficient:
            filenames = ", ".join(document["filename"] for document in documents[:3])
            answer = (
                "I could not find a passage in the selected documents that answers this "
                "question, so I will not guess. " + reason
            )
            self._record(question, answer, conversation_id, scope_ids, [], AnswerMode.INSUFFICIENT, started)
            return AnswerResponse(
                question=question,
                answer=answer,
                answer_mode=AnswerMode.INSUFFICIENT,
                insufficient_evidence=True,
                citations=[],
                retrieved_count=len(retrieved),
                latency_ms=(time.perf_counter() - started) * 1000,
                embedding_provider=self.container.embedder.name,
                conversation_id=conversation_id,
                notice=(
                    f"Searched {len(documents)} document(s) ({filenames}). "
                    f"Best match scored {best:.3f}. {reason}"
                ),
            )

        draft = self.container.answerer.answer(question, retrieved, self.settings.answer_max_sentences)

        if draft.mode == AnswerMode.INSUFFICIENT:
            # No answer means no citation: attaching a reference to a refusal invites
            # the reader to treat unsupported text as sourced.
            citations: List[Citation] = []
        else:
            used = draft.used_citations or None
            citations = to_citations(retrieved, question, used, draft.used_sentences)
            if not citations:
                # Provider answered without citing; fall back to exposing the evidence.
                citations = to_citations(retrieved, question, {1}, draft.used_sentences)

        latency_ms = (time.perf_counter() - started) * 1000
        self._record(question, draft.text, conversation_id, scope_ids, citations, draft.mode, started)

        return AnswerResponse(
            question=question,
            answer=draft.text,
            answer_mode=draft.mode,
            insufficient_evidence=draft.mode == AnswerMode.INSUFFICIENT,
            citations=citations,
            retrieved_count=len(retrieved),
            latency_ms=latency_ms,
            embedding_provider=self.container.embedder.name,
            conversation_id=conversation_id,
            notice=draft.notice,
        )

    def _record(
        self,
        question: str,
        answer: str,
        conversation_id: Optional[str],
        document_ids: List[str],
        citations: List[Citation],
        mode: AnswerMode,
        started: float,
    ) -> None:
        """Persist the exchange and log timing, without failing the request."""
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            self.container.db.log_event(
                "answer",
                {
                    "question": question[:200],
                    "mode": mode.value,
                    "citations": len(citations),
                    "documents": len(document_ids),
                },
                latency_ms=latency_ms,
            )
            if not conversation_id:
                return
            if self.container.db.get_conversation(conversation_id) is None:
                logger.warning("Conversation %s not found; skipping persistence.", conversation_id)
                return
            self.container.db.add_message(conversation_id, "user", question)
            self.container.db.add_message(
                conversation_id,
                "assistant",
                answer,
                citations=[citation.model_dump() for citation in citations],
                answer_mode=mode.value,
            )
            self.container.db.touch_conversation(conversation_id)
        except Exception as exc:  # noqa: BLE001 - persistence must not break answering
            logger.error("Could not persist the conversation exchange: %s", exc)

    # -- conversations -------------------------------------------------
    def ensure_conversation(self, document_ids: Sequence[str], title: str = "") -> str:
        if not title:
            names = [
                self.container.db.get_document(document_id)["filename"]
                for document_id in document_ids
                if self.container.db.get_document(document_id) is not None
            ]
            title = f"Chat about {names[0]}" if len(names) == 1 else f"Chat about {len(names)} documents"
        return self.container.db.create_conversation(title=title, document_ids=list(document_ids))
