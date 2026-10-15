import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DocumentDropzone } from "@/components/DocumentDropzone";
import { DocumentTable } from "@/components/DocumentTable";
import { Button } from "@/components/ui/Button";
import { Card, Metric } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ErrorState, Notice } from "@/components/ui/Feedback";
import { ProgressBar } from "@/components/ui/Pill";
import { useApp } from "@/context/AppContext";
import { useAsync } from "@/hooks/useAsync";
import { useMutation } from "@/hooks/useMutation";
import { usePolling } from "@/hooks/usePolling";
import { formatBytes } from "@/services/format";
import type { ApiError } from "@/services/client";
import type { DocumentSummary, SettingsResponse } from "@/types/api";

const FALLBACK_EXTENSIONS = ["pdf", "txt", "md", "docx"];
const FALLBACK_MAX_MB = 25;

/** `usePolling` exposes its error as `unknown`; normalise it for display. */
function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

/**
 * Screen 2 — the upload workspace.
 *
 * The document list is polled while any document is still queued or processing,
 * so a newly uploaded file moves from "Queued" to "Ready" on its own. Deletion
 * always goes through a confirmation that names the document.
 */
export function DocumentsPage() {
  const navigate = useNavigate();
  const { api, pushToast } = useApp();

  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [pendingDelete, setPendingDelete] = useState<DocumentSummary | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [lastUploadId, setLastUploadId] = useState<string | null>(null);


  const documents = usePolling<DocumentSummary[]>(() => api.listDocuments(), {
    intervalMs: 1500,
    maxIntervalMs: 6000,
    refreshKey,
    // Once nothing is queued or processing there is nothing left to watch.
    stopWhen: (value) =>
      Array.isArray(value) &&
      value.every((document: DocumentSummary) => document.status !== "queued" && document.status !== "processing"),
  });

  // Settings drive the client-side upload guard rails; failure here is not fatal,
  // because the backend re-validates every upload independently.
  const settings = useAsync<SettingsResponse>(() => api.getSettings(), [api]);

  const upload = useMutation(async (files: File[]) => {
    const created: DocumentSummary[] = [];
    for (const file of files) {
      const response = await api.uploadDocument(file);
      created.push(response.document);
    }
    return created;
  });

  const remove = useMutation(async (document: DocumentSummary) => api.deleteDocument(document.id));

  const list = useMemo(() => documents.value ?? [], [documents.value]);
  const processing = list.filter((document) => document.status === "queued" || document.status === "processing");
  const readyCount = list.filter((document) => document.status === "ready").length;
  const failedCount = list.filter((document) => document.status === "failed").length;
  const totalBytes = list.reduce((sum, document) => sum + document.size_bytes, 0);

  // The API reports extensions with a leading dot (".pdf"); the browser-side guard
  // compares bare extension names, so normalise once here.
  const allowedExtensions = useMemo(
    () =>
      (settings.data?.allowed_extensions ?? FALLBACK_EXTENSIONS)
        .map((extension) => extension.replace(/^\./, "").toLowerCase())
        .filter(Boolean),
    [settings.data?.allowed_extensions],
  );
  const maxBytes = (settings.data?.max_upload_mb ?? FALLBACK_MAX_MB) * 1024 * 1024;

  const reload = useCallback(() => setRefreshKey((value) => value + 1), []);

  async function handleFiles(files: File[]) {
    const result = await upload.run(files);
    if (result && result.length > 0) {
      setLastUploadId(result[result.length - 1]!.id);
      pushToast({
        tone: "success",
        title: `Uploaded ${result.length} file${result.length === 1 ? "" : "s"}`,
        message: "Processing has started. Progress is on the Processing screen.",
      });
      reload();
      // Selecting the newest upload makes the Processing screen useful immediately.
      setSelectedIds(result.map((document) => document.id));
    }
  }

  async function handleDelete() {
    if (!pendingDelete) return;
    setBusyId(pendingDelete.id);
    const result = await remove.run(pendingDelete);
    setBusyId(null);
    if (result) {
      pushToast({
        tone: "success",
        title: `Deleted ${pendingDelete.filename}`,
        message: `Removed ${result.vectors_removed} vector${result.vectors_removed === 1 ? "" : "s"} and ${result.files_removed} stored file${result.files_removed === 1 ? "" : "s"}.`,
      });
      setSelectedIds((current) => current.filter((id) => id !== pendingDelete.id));
      setPendingDelete(null);
      reload();
    }
  }

  const deleteError = remove.error as ApiError | null;

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <span>Screen 02</span>
        <span className="breadcrumbs__sep">/</span>
        <span>Document workspace</span>
      </div>

      <header className="page-header">
        <h1>Documents</h1>
        <p className="page-header__lede">
          Add PDF, TXT or Markdown and DOCX files. Files are copied into this application&apos;s local data directory,
          extracted, chunked and embedded on this machine. Nothing is uploaded to a third party.
        </p>
      </header>

      <section className="section" aria-labelledby="upload-heading">
        <Card title="Add documents" titleId="upload-heading">
          <DocumentDropzone
            onFiles={handleFiles}
            allowedExtensions={allowedExtensions}
            maxBytes={maxBytes}
            busy={upload.pending}
          />
          {upload.pending ? (
            <div style={{ marginTop: "var(--space-3)" }}>
              <ProgressBar indeterminate label="Uploading and queueing" detail="Waiting for the server to accept the file" />
            </div>
          ) : null}
          {upload.error ? (
            <div style={{ marginTop: "var(--space-3)" }}>
              <ErrorState error={upload.error} title="Upload failed" onRetry={upload.reset} />
            </div>
          ) : null}
          {lastUploadId ? (
            <div className="row" style={{ marginTop: "var(--space-3)" }}>
              <Button size="small" onClick={() => navigate(`/processing/${lastUploadId}`)}>
                Watch it being processed
              </Button>
            </div>
          ) : null}
        </Card>
      </section>

      <section className="section" >
        <Card>
          <div className="grid grid--4">
            <Metric label="Documents" value={list.length} note="Total stored on this machine" />
            <Metric label="Ready" value={readyCount} note="Available for questions" />
            <Metric label="In progress" value={processing.length} note="Extracting, embedding or indexing" />
            <Metric label="Failed" value={failedCount} note="These can be retried" />
          </div>
          <p className="text-small text-dim" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
            Total original file size on disk: {formatBytes(totalBytes)}
          </p>
        </Card>
      </section>

      {processing.length > 0 ? (
        <section className="section">
          <Notice>
            {processing.length} document{processing.length === 1 ? " is" : "s are"} still being processed. This list
            updates itself every couple of seconds.
          </Notice>
        </section>
      ) : null}

      <section className="section" aria-labelledby="list-heading">
        <Card
          title="Document library"
          titleId="list-heading"
          hint="Select two or more rows to question them together."
          actions={
            <>
              <Button
                size="small"
                onClick={() => navigate(`/chat?docs=${selectedIds.join(",")}`)}
                disabled={selectedIds.length === 0}
              >
                Ask {selectedIds.length > 0 ? `across ${selectedIds.length}` : "across selected"}
              </Button>
              <Button size="small" variant="ghost" onClick={reload} loading={documents.value === null}>
                Refresh
              </Button>
            </>
          }
        >
          {documents.error && documents.value === null ? (
            <ErrorState error={asError(documents.error)} title="Could not load documents" onRetry={reload} />
          ) : (
            <DocumentTable
              documents={list}
              selectedIds={selectedIds}
              onToggleSelected={(id) =>
                setSelectedIds((current) =>
                  current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
                )
              }
              onToggleAll={setSelectedIds}
              onAsk={(id) => navigate(`/chat?docs=${id}`)}
              onInspect={(id) => navigate(`/processing/${id}`)}
              onDelete={setPendingDelete}
              busyId={busyId}
            />
          )}
        </Card>
      </section>

      {deleteError ? <ErrorState error={deleteError} title="Deletion failed" /> : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this document?"
        confirmLabel="Delete permanently"
        danger
        pending={remove.pending}
        onCancel={() => {
          setPendingDelete(null);
          remove.reset();
        }}
        onConfirm={handleDelete}
      >
        <p style={{ marginTop: 0 }}>
          <strong>{pendingDelete?.filename}</strong> will be removed from the document store, its chunks deleted from the
          vector index, and its stored file removed from disk.
        </p>
        <p style={{ marginBottom: 0 }}>This cannot be undone. Questions already answered keep their saved citations.</p>
      </ConfirmDialog>
    </div>
  );
}
