import { useMemo, useState } from "react";

import type { DocumentSummary } from "@/types/api";
import { formatBytes, formatRelative } from "@/services/format";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/Feedback";
import { StatusPill } from "./ui/Pill";

type SortKey = "filename" | "size" | "status" | "created";

export interface DocumentTableProps {
  documents: DocumentSummary[];
  /** Ids currently selected for multi-document questions. */
  selectedIds: string[];
  onToggleSelected: (id: string) => void;
  onToggleAll: (ids: string[]) => void;
  onAsk: (id: string) => void;
  onInspect: (id: string) => void;
  onDelete: (document: DocumentSummary) => void;
  busyId?: string | null;
}

/**
 * Sortable, selectable table of indexed documents.
 *
 * Rows are keyboard reachable, the checkbox column carries its own accessible
 * label, and every action button names the document it acts on so screen-reader
 * users can tell ten identical "Delete" buttons apart.
 */
export function DocumentTable({
  documents,
  selectedIds,
  onToggleSelected,
  onToggleAll,
  onAsk,
  onInspect,
  onDelete,
  busyId,
}: DocumentTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("created");
  const [ascending, setAscending] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...documents];
    copy.sort((left, right) => {
      let comparison = 0;
      switch (sortKey) {
        case "filename":
          comparison = left.filename.localeCompare(right.filename);
          break;
        case "size":
          comparison = left.size_bytes - right.size_bytes;
          break;
        case "status":
          comparison = left.status.localeCompare(right.status);
          break;
        case "created":
        default:
          comparison = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
      }
      return ascending ? comparison : -comparison;
    });
    return copy;
  }, [documents, sortKey, ascending]);

  function header(key: SortKey, label: string) {
    const active = sortKey === key;
    return (
      <th scope="col" aria-sort={active ? (ascending ? "ascending" : "descending") : "none"}>
        <button
          type="button"
          className="btn btn--ghost btn--small"
          style={{ padding: "4px 8px", minHeight: 30 }}
          onClick={() => {
            if (active) setAscending((value) => !value);
            else {
              setSortKey(key);
              setAscending(true);
            }
          }}
        >
          {label}
          <span aria-hidden="true">{active ? (ascending ? "▲" : "▼") : "↕"}</span>
        </button>
      </th>
    );
  }

  if (documents.length === 0) {
    return (
      <EmptyState title="No documents yet">
        Upload a PDF, TXT or DOCX file above. Processing runs entirely on this machine, so nothing is sent to a
        third-party service.
      </EmptyState>
    );
  }

  const allSelected = documents.length > 0 && selectedIds.length === documents.length;

  return (
    <div className="table-scroll">
      <table className="doc-table">
        <caption>
          {documents.length} document{documents.length === 1 ? "" : "s"} · select rows to ask across several at once
        </caption>
        <thead>
          <tr>
            <th scope="col" style={{ width: 40 }}>
              <input
                type="checkbox"
                checked={allSelected}
                aria-label="Select all documents"
                onChange={() => onToggleAll(allSelected ? [] : documents.map((document) => document.id))}
              />
            </th>
            {header("filename", "Document")}
            {header("status", "Status")}
            <th scope="col">Pages</th>
            <th scope="col">Chunks</th>
            {header("size", "Size")}
            {header("created", "Uploaded")}
            <th scope="col" style={{ textAlign: "right" }}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((document) => (
            <tr key={document.id} data-testid={`doc-row-${document.id}`}>
              <td>
                <input
                  type="checkbox"
                  checked={selectedIds.includes(document.id)}
                  onChange={() => onToggleSelected(document.id)}
                  aria-label={`Include ${document.filename} in multi-document questions`}
                />
              </td>
              <td>
                <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{document.filename}</div>
                <div className="text-dim mono" style={{ fontSize: "0.72rem" }}>
                  {document.id}
                </div>
                {document.error ? (
                  <div className="text-small" style={{ color: "var(--rose)" }}>
                    {document.error}
                  </div>
                ) : null}
              </td>
              <td>
                <StatusPill status={document.status} />
              </td>
              <td className="mono">{document.page_count ?? "—"}</td>
              <td className="mono">{document.chunk_count}</td>
              <td className="mono">{formatBytes(document.size_bytes)}</td>
              <td className="text-small text-muted">{formatRelative(document.created_at)}</td>
              <td>
                <div className="doc-table__actions">
                  <Button
                    size="small"
                    variant="ghost"
                    onClick={() => onInspect(document.id)}
                    aria-label={`Open processing details for ${document.filename}`}
                  >
                    Pipeline
                  </Button>
                  <Button
                    size="small"
                    onClick={() => onAsk(document.id)}
                    disabled={document.status !== "ready"}
                    aria-label={`Ask questions about ${document.filename}`}
                  >
                    Ask
                  </Button>
                  <Button
                    size="small"
                    variant="danger"
                    loading={busyId === document.id}
                    loadingLabel="Deleting…"
                    onClick={() => onDelete(document)}
                    aria-label={`Delete ${document.filename}`}
                  >
                    Delete
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
