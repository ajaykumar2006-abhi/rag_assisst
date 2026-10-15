"""Chunking with metadata preservation.

Turns extracted sections into overlapping chunks sized for embedding models.
Every chunk keeps the information a citation needs: document id, ordinal, the
source page (when the format has pages), and character offsets into the
document's normalised text.

Boundaries prefer, in order: paragraph break, sentence break, then word break --
so chunks stay semantically coherent instead of cutting mid-sentence. Text is
never silently dropped: the final chunk of a section always reaches the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .extraction import ExtractedSection
from .text_utils import estimate_tokens

# How far back from the ideal cut point we are willing to look for a nicer break.
_BREAK_SEARCH_RATIO = 0.45


@dataclass
class Chunk:
    id: str
    document_id: str
    ordinal: int
    text: str
    page: int | None
    char_start: int
    char_end: int
    token_estimate: int

    def to_record(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "token_estimate": self.token_estimate,
        }


def make_chunk_id(document_id: str, ordinal: int) -> str:
    return f"{document_id}::{ordinal:05d}"


def _best_break(text: str, start: int, ideal_end: int, minimum: int) -> int:
    """Pick a boundary in ``[minimum, ideal_end]`` favouring paragraphs/sentences."""
    if ideal_end >= len(text):
        return len(text)

    window = text[minimum:ideal_end]
    if not window:
        return ideal_end

    for separator in ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "):
        index = window.rfind(separator)
        if index != -1:
            candidate = minimum + index + (len(separator) if separator.strip() else 0)
            if candidate > minimum:
                return candidate
    return ideal_end


def chunk_sections(
    sections: Sequence[ExtractedSection],
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
    max_chunks: int,
) -> List[Chunk]:
    """Split extracted sections into overlapping, metadata-carrying chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    chunks: List[Chunk] = []
    ordinal = 0
    document_offset = 0

    for section in sections:
        text = section.text or ""
        if not text.strip():
            # Preserve offset continuity even for empty pages.
            document_offset += len(text) + 2
            continue

        start = 0
        length = len(text)
        while start < length:
            ideal_end = min(start + chunk_size, length)
            minimum = start + max(1, int(chunk_size * (1 - _BREAK_SEARCH_RATIO)))
            minimum = min(minimum, ideal_end)
            end = _best_break(text, start, ideal_end, minimum) if ideal_end < length else length
            end = max(end, start + 1)

            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    Chunk(
                        id=make_chunk_id(document_id, ordinal),
                        document_id=document_id,
                        ordinal=ordinal,
                        text=piece,
                        page=section.page,
                        char_start=document_offset + start,
                        char_end=document_offset + end,
                        token_estimate=estimate_tokens(piece),
                    )
                )
                ordinal += 1
                if len(chunks) >= max_chunks:
                    return chunks

            if end >= length:
                break
            # Step forward, keeping ``chunk_overlap`` characters of context.
            start = max(end - chunk_overlap, start + 1)

        document_offset += length + 2  # account for the "\n\n" joiner in ExtractionResult.text

    return chunks


def pages_covered(chunks: Sequence[Chunk]) -> int:
    """Number of distinct pages represented across chunks."""
    return len({chunk.page for chunk in chunks if chunk.page is not None})
