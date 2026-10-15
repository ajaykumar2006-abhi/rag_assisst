import type { Citation } from "@/types/api";
import { formatMetric } from "@/services/format";

export interface CitationCardProps {
  citation: Citation;
  onOpen?: (citation: Citation) => void;
}

/**
 * One retrieved source.
 *
 * The excerpt is the verbatim chunk text the backend retrieved — it is never
 * rewritten or summarised — and the score breakdown is shown so a reader can see
 * *why* this passage surfaced (vector similarity vs keyword overlap).
 */
export function CitationCard({ citation, onOpen }: CitationCardProps) {
  const location = citation.page !== null ? `page ${citation.page}` : "page not available";

  return (
    <article className="citation" data-testid={`citation-${citation.index}`}>
      <div className="citation__head">
        <span className="pill pill--extractive" aria-label={`Source ${citation.index}`}>
          [{citation.index}]
        </span>
        <span style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{citation.filename}</span>
        <span className="text-dim">· {location}</span>
        <span className="text-dim mono" style={{ fontSize: "0.72rem" }}>
          chunk {citation.chunk_id}
        </span>
      </div>
      <blockquote className="citation__excerpt">{citation.excerpt}</blockquote>
      <div className="citation__scores">
        <span title="Blended relevance score used for ranking">score {formatMetric(citation.score, 4)}</span>
        <span title="Cosine similarity against the document vector index">vector {formatMetric(citation.dense_score, 4)}</span>
        <span title="Keyword-overlap component of the blended score">
          lexical {formatMetric(citation.lexical_score, 4)}
        </span>
        <span className="spacer" />
        {onOpen ? (
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={() => onOpen(citation)}
            aria-label={`Open the full context for source ${citation.index} of ${citation.filename}`}
          >
            Open context
          </button>
        ) : null}
      </div>
    </article>
  );
}
