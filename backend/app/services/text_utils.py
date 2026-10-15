"""Small, dependency-free text helpers shared across services."""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Set

# Abbreviations that should not end a sentence.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "fig", "no", "approx", "inc", "ltd", "co", "dept", "est", "al", "cf", "ca",
    "u.s", "u.k", "a.m", "p.m",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")

# Extremely common words carry no retrieval signal on their own.
_STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "of", "at", "by", "for", "with",
    "about", "into", "to", "from", "in", "on", "is", "are", "was", "were", "be",
    "been", "being", "it", "its", "this", "that", "these", "those", "as", "so",
    "than", "then", "there", "here", "what", "which", "who", "whom", "whose",
    "how", "why", "when", "where", "do", "does", "did", "done", "can", "could",
    "should", "would", "will", "shall", "may", "might", "must", "i", "you", "he",
    "she", "they", "we", "them", "us", "his", "her", "their", "our", "your", "my",
    "me", "not", "no", "yes", "have", "has", "had", "also", "any", "all", "some",
}


def tokenize(text: str) -> List[str]:
    """Lower-cased word tokens."""
    return [match.group(0).lower() for match in _WORD.finditer(text or "")]


def content_tokens(text: str) -> List[str]:
    """Tokens with stopwords removed, used for keyword overlap scoring."""
    return [token for token in tokenize(text) if token not in _STOPWORDS and len(token) > 1]


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 characters per token) for budgeting."""
    return max(1, len(text or "") // 4)


def split_sentences(text: str) -> List[str]:
    """Split a paragraph into sentences, protecting common abbreviations."""
    text = (text or "").strip()
    if not text:
        return []

    candidates = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    sentences: List[str] = []
    for candidate in candidates:
        if sentences:
            previous = sentences[-1]
            tail = previous.rsplit(" ", 1)[-1].rstrip(".!?").lower()
            if tail in _ABBREVIATIONS or len(previous) < 25:
                # Abbreviation or a stub fragment: glue it onto the previous sentence.
                sentences[-1] = f"{previous} {candidate}".strip()
                continue
        sentences.append(candidate)
    return sentences


def keyword_overlap(question_tokens: Sequence[str], text: str) -> float:
    """Fraction of distinct question tokens present in ``text`` (0..1)."""
    query = {token for token in question_tokens if token not in _STOPWORDS}
    if not query:
        return 0.0
    haystack = set(tokenize(text))
    return len(query & haystack) / len(query)


def extract_keywords(text: str, limit: int = 12) -> List[str]:
    """Most frequent content words, used for lightweight titles/summaries."""
    counts: dict[str, int] = {}
    for token in content_tokens(text):
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:limit]]


def truncate(text: str, limit: int, suffix: str = "...") -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - len(suffix))].rstrip()
    # Avoid slicing mid-word when a space is available nearby.
    if " " in cut[max(0, len(cut) - 20):]:
        cut = cut.rsplit(" ", 1)[0]
    return f"{cut}{suffix}"


def join_phrases(items: Iterable[str]) -> str:
    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"
