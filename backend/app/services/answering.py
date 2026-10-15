"""Answer generation providers.

The application must be useful with no API key at all, so the default path is
**extractive**: it selects the sentences from the retrieved passages that best
match the question and returns them *verbatim*, each tagged with the citation
marker of the chunk it came from. Nothing is paraphrased, invented or quoted
from memory, which is exactly what makes the citations verifiable.

An optional OpenAI-compatible provider can be configured for fluent generated
answers. It is given only the retrieved passages, is told to cite them, and its
output is returned as ``generative`` mode so the UI never presents model prose
as if it were a document quotation.

Both providers return :class:`AnswerDraft`, which carries the text plus the set
of citation markers actually used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

import httpx

from ..core.errors import ProviderConfigError
from ..schemas.models import AnswerMode
from .retrieval import RetrievedChunk
from .text_utils import content_tokens, keyword_overlap, split_sentences, truncate

logger = logging.getLogger(__name__)

MIN_SENTENCE_CHARS = 40
REQUEST_TIMEOUT_SECONDS = 60.0

# A sentence only counts as part of the answer if enough of the question's content
# words appear in it. Requiring *some* overlap is not enough: for a six-word
# question a sentence sharing a single word scores 0.17 and dilutes the answer
# with tangential text. The floor also scales with the best sentence found, so a
# short question that is answered by one strong sentence does not pad itself out
# with weak neighbours.
MIN_SENTENCE_OVERLAP = 0.25
RELATIVE_SENTENCE_OVERLAP = 0.5


@dataclass
class AnswerDraft:
    text: str
    mode: AnswerMode
    used_citations: Set[int] = field(default_factory=set)
    #: citation index -> the exact sentences quoted from that chunk. Providers that
    #: copy text verbatim fill this in so the citation excerpt can be anchored on
    #: the sentence actually used, rather than on whichever sentence scores highest.
    used_sentences: Dict[int, List[str]] = field(default_factory=dict)
    notice: Optional[str] = None


class Answerer:
    """Interface for answer providers."""

    name = "base"
    mode = AnswerMode.EXTRACTIVE
    description = ""

    def answer(self, question: str, chunks: Sequence[RetrievedChunk], max_sentences: int) -> AnswerDraft:
        raise NotImplementedError

    def availability(self) -> tuple[bool, str]:
        """Return (is_available, reason_if_not)."""
        return True, ""


# ---------------------------------------------------------------------------
# Local extractive answerer (default)
# ---------------------------------------------------------------------------


class ExtractiveAnswerer(Answerer):
    """Evidence-only answering with zero external dependencies."""

    name = "extractive"
    mode = AnswerMode.EXTRACTIVE
    description = (
        "Local extractive answering. The most question-relevant sentences are copied "
        "verbatim from the retrieved passages; no text is generated or paraphrased."
    )

    def answer(self, question: str, chunks: Sequence[RetrievedChunk], max_sentences: int) -> AnswerDraft:
        if not chunks:
            return AnswerDraft(
                text=(
                    "I could not find any passage in the selected documents that addresses this "
                    "question, so I am not able to answer it from the available evidence."
                ),
                mode=AnswerMode.INSUFFICIENT,
                notice="No passages were retrieved.",
            )

        query_tokens = content_tokens(question)
        candidates: List[tuple[float, int, int, str, int]] = []
        for citation_index, chunk in enumerate(chunks, start=1):
            chunk_relevance = keyword_overlap(query_tokens, chunk.text)
            for sentence_index, sentence in enumerate(split_sentences(chunk.text)):
                if len(sentence) < MIN_SENTENCE_CHARS:
                    continue
                overlap = keyword_overlap(query_tokens, sentence)
                if overlap <= 0:
                    continue
                score = (
                    overlap * 0.70
                    + chunk_relevance * 0.15
                    + min(max(chunk.fused_score, 0.0), 1.0) * 0.15
                )
                candidates.append((score, citation_index, sentence_index, sentence, len(sentence)))

        if not candidates:
            best = chunks[0]
            return AnswerDraft(
                text=(
                    "I could not find a sentence in the retrieved passages that answers this "
                    "question, so I am not able to answer it from the available evidence."
                ),
                mode=AnswerMode.INSUFFICIENT,
                used_citations=set(),
                notice=(
                    "No sentence in the retrieved passages shared meaningful vocabulary with "
                    f"the question. Closest match scored {best.fused_score:.3f}."
                ),
            )

        # Drop sentences that are only tangentially related to the question, then
        # remove duplicates: the same sentence can appear in two chunks when a
        # document is stored in two formats, and repeating it wastes the reader's
        # attention and inflates the citation count.
        best_overlap = max(keyword_overlap(query_tokens, sentence) for *_rest, sentence, _length in candidates)
        floor = max(MIN_SENTENCE_OVERLAP, best_overlap * RELATIVE_SENTENCE_OVERLAP)
        filtered = [
            candidate
            for candidate in candidates
            if keyword_overlap(query_tokens, candidate[3]) >= floor
        ]

        filtered.sort(key=lambda item: (-item[0], item[1], item[2]))
        chosen: List[tuple[float, int, int, str, int]] = []
        seen: Set[str] = set()
        for candidate in filtered:
            fingerprint = " ".join(candidate[3].lower().split())
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            chosen.append(candidate)
            if len(chosen) >= max(1, max_sentences):
                break

        # Present the evidence in document order so it reads naturally.
        chosen.sort(key=lambda item: (item[1], item[2]))

        used: Set[int] = set()
        used_sentences: Dict[int, List[str]] = {}
        parts: List[str] = []
        for _score, citation_index, _sentence_index, sentence, _length in chosen:
            cleaned = sentence.strip().rstrip(".")
            marker = f"[{citation_index}]"
            used.add(citation_index)
            used_sentences.setdefault(citation_index, []).append(sentence.strip())
            if cleaned.endswith(marker):
                parts.append(f"{cleaned}.")
            else:
                parts.append(f"{cleaned} {marker}.")

        return AnswerDraft(
            text=" ".join(parts),
            mode=AnswerMode.EXTRACTIVE,
            used_citations=used,
            used_sentences=used_sentences,
            notice=(
                "Extractive answer: every sentence above is copied verbatim from the cited "
                "passages. Nothing was generated or reworded."
            ),
        )


# ---------------------------------------------------------------------------
# Optional external provider
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a careful research assistant. Answer ONLY from the numbered context "
    "passages provided. Cite each claim with the bracketed passage numbers, e.g. [1]. "
    "Never invent facts, quotations, page numbers or citation numbers. If the context "
    "does not contain the answer, say plainly that the provided documents do not "
    "contain enough information. Keep the answer concise and factual."
)


class OpenAICompatibleAnswerer(Answerer):
    """Optional generative answering against an OpenAI-compatible chat endpoint."""

    name = "openai_compatible"
    mode = AnswerMode.GENERATIVE
    description = (
        "Optional external provider. Retrieved passages are sent to a configured "
        "OpenAI-compatible chat endpoint, which composes a grounded answer."
    )

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""

    def availability(self) -> tuple[bool, str]:
        missing = [
            label
            for label, value in (
                ("LLM_BASE_URL", self.base_url),
                ("LLM_API_KEY", self.api_key),
                ("LLM_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            return False, f"Missing configuration: {', '.join(missing)}"
        return True, ""

    def answer(self, question: str, chunks: Sequence[RetrievedChunk], max_sentences: int) -> AnswerDraft:
        available, reason = self.availability()
        if not available:
            raise ProviderConfigError(
                f"The generative answer provider is selected but not configured. {reason}. "
                "Set the missing variables in .env, or switch ANSWER_PROVIDER=extractive."
            )
        if not chunks:
            return AnswerDraft(
                text="The provided documents do not contain enough information to answer this question.",
                mode=AnswerMode.INSUFFICIENT,
                notice="No passages were retrieved.",
            )

        context_blocks = []
        for index, chunk in enumerate(chunks, start=1):
            location = f" (page {chunk.page})" if chunk.page else ""
            context_blocks.append(f"[{index}] {chunk.document_filename}{location}:\n{chunk.text}")
        context = "\n\n".join(context_blocks)

        payload = {
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nNumbered context passages:\n\n{context}",
                },
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise ProviderConfigError(
                f"Could not reach the configured answer provider at {self.base_url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = truncate(response.text or "", 300)
            raise ProviderConfigError(
                f"The answer provider returned HTTP {response.status_code}. {detail}"
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderConfigError(
                "The answer provider returned an unexpected response shape."
            ) from exc

        used: Set[int] = set()
        for index in range(1, len(chunks) + 1):
            if f"[{index}]" in text:
                used.add(index)

        insufficient = any(
            phrase in text.lower()
            for phrase in ("no information", "not enough information", "cannot answer", "do not contain")
        )
        if not used and not insufficient:
            # The model answered without citing: treat it as unsupported.
            return AnswerDraft(
                text=text,
                mode=AnswerMode.GENERATIVE,
                used_citations=set(),
                notice=(
                    "The provider returned an answer without citation markers. Review the "
                    "retrieved passages below before trusting it."
                ),
            )

        return AnswerDraft(
            text=text,
            mode=AnswerMode.INSUFFICIENT if insufficient else AnswerMode.GENERATIVE,
            used_citations=used,
            notice=(
                "Generated answer from an external provider, grounded in the passages below. "
                "Verify against the cited sources."
            ),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_answerer(settings) -> Answerer:
    """Create the answerer named by configuration."""
    provider = settings.answer_provider
    if provider == "openai_compatible":
        return OpenAICompatibleAnswerer(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    return ExtractiveAnswerer()


def answerer_status(settings) -> Dict[str, object]:
    """Non-secret description of the answering configuration for the UI."""
    answerer = build_answerer(settings)
    available, reason = answerer.availability()
    return {
        "provider": answerer.name,
        "mode": answerer.mode.value,
        "description": answerer.description,
        "available": available,
        "reason": reason,
    }
