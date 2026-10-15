import { useEffect, useRef } from "react";

import type { Citation } from "@/types/api";
import { formatMetric } from "@/services/format";
import { Button } from "./ui/Button";

/**
 * Focus-trapped modal showing everything known about one retrieved source: the
 * full retrieved excerpt, where it came from in the original file (character
 * offsets and page when the extractor could determine it) and the exact scores
 * that put it in the result set.
 */
export function SourceViewer({
  citation,
  onClose,
  onOpenDocument,
}: {
  citation: Citation | null;
  onClose: () => void;
  onOpenDocument?: (documentId: string) => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!citation) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>("button, [href]");
    focusables?.[0]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), [href]"));
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [citation, onClose]);

  if (!citation) return null;

  return (
    <div
      className="viewer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="viewer__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-viewer-title"
        ref={panelRef}
        data-testid="source-viewer"
      >
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 id="source-viewer-title" style={{ marginBottom: 4 }}>
              Source [{citation.index}] · {citation.filename}
            </h2>
            <p className="text-muted text-small" style={{ margin: 0 }}>
              {citation.page !== null ? `Page ${citation.page} · ` : "Page unavailable · "}
              characters {citation.char_start}–{citation.char_end} of the extracted text
            </p>
          </div>
          <Button variant="ghost" size="small" onClick={onClose} aria-label="Close source context">
            Close
          </Button>
        </div>

        <h3 style={{ marginTop: "var(--space-5)" }}>Retrieved passage (verbatim)</h3>
        <blockquote className="citation__excerpt" style={{ fontSize: "0.95rem" }}>
          {citation.excerpt}
        </blockquote>

        <h3 style={{ marginTop: "var(--space-5)" }}>Why this passage matched</h3>
        <ul className="hint-list">
          <li>
            Blended relevance score: <span className="mono">{formatMetric(citation.score, 6)}</span> — dense and lexical
            components combined with the weights configured on the Settings screen.
          </li>
          <li>
            Vector similarity: <span className="mono">{formatMetric(citation.dense_score, 6)}</span> (cosine against the
            indexed embedding).
          </li>
          <li>
            Keyword overlap: <span className="mono">{formatMetric(citation.lexical_score, 6)}</span> (distinct question
            tokens present in this chunk).
          </li>
          <li>
            Chunk id: <span className="mono">{citation.chunk_id}</span> (document id{" "}
            <span className="mono">{citation.document_id}</span>).
          </li>
        </ul>

        {citation.page === null ? (
          <p className="text-small text-dim">
            Page numbers are only available for PDFs that carry an extractable text layer. For TXT and DOCX files the
            character offsets above are the precise locator.
          </p>
        ) : null}

        {onOpenDocument ? (
          <div className="row" style={{ marginTop: "var(--space-4)" }}>
            <Button onClick={() => onOpenDocument(citation.document_id)}>
              Open this document&apos;s pipeline view
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
