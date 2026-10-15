import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, Metric } from "@/components/ui/Card";
import { EmptyState, ErrorState, Notice, Spinner } from "@/components/ui/Feedback";
import { ProgressBar, StatusPill } from "@/components/ui/Pill";
import { StageTimeline } from "@/components/ui/StageTimeline";
import { useApp } from "@/context/AppContext";
import { useAsync } from "@/hooks/useAsync";
import { useMutation } from "@/hooks/useMutation";
import { usePolling } from "@/hooks/usePolling";
import { formatBytes, formatDateTime, formatMilliseconds, statusLabel } from "@/services/format";
import type { Citation, DocumentStatusResponse, DocumentSummary, SourceResponse } from "@/types/api";

function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

/** Decorative "observatory" ring that reflects the real document status. */
function OrbitVisual({ state }: { state: DocumentSummary["status"] }) {
  return (
    <div
      className={`orbit${state === "ready" ? " orbit--done" : ""}${state === "failed" ? " orbit--failed" : ""}`}
      role="img"
      aria-label={`Processing visual for status ${statusLabel(state)}`}
    >
      <div className="orbit__ring">
        <span className="orbit__dot" />
      </div>
      <div className="orbit__ring orbit__ring--inner">
        <span className="orbit__dot orbit__dot--inner" />
      </div>
      <div className="orbit__core" />
    </div>
  );
}

/**
 * Screen 3 — the processing observatory.
 *
 * Without `:id` it lists every document with its live status; with an id it shows
 * the seven real pipeline stages, extracted-text statistics, the stored chunks
 * and a retry action for failed runs. Every value on this screen comes from the
 * backend — nothing is simulated.
 */
export function ProcessingPage() {
  const { id } = useParams<{ id: string }>();
  const [refreshKey, setRefreshKey] = useState(0);

  if (!id) {
    return (
      <ProcessingOverview
        refreshKey={refreshKey}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      />
    );
  }
  return <ProcessingDetail documentId={id} />;
}

function ProcessingOverview({ refreshKey, onRefresh }: { refreshKey: number; onRefresh: () => void }) {
  const { api } = useApp();
  const navigate = useNavigate();

  const documents = usePolling<DocumentSummary[]>(() => api.listDocuments(), {
    intervalMs: 1500,
    maxIntervalMs: 6000,
    refreshKey,
    stopWhen: (value) =>
      Array.isArray(value) &&
      value.every((document: DocumentSummary) => document.status !== "queued" && document.status !== "processing"),
  });

  const list = documents.value ?? [];
  const active = list.filter((document) => document.status === "queued" || document.status === "processing");

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <span>Screen 03</span>
        <span className="breadcrumbs__sep">/</span>
        <span>Processing pipeline</span>
      </div>

      <header className="page-header">
        <h1>Processing pipeline</h1>
        <p className="page-header__lede">
          Each document moves through seven stages: validate, extract, structure, chunk, embed, index and verify. Open a
          document to watch its stages advance; the numbers shown are the backend&apos;s own progress values.
        </p>
        <div className="row">
          <Button variant="primary" onClick={() => navigate("/documents")}>
            Add a document
          </Button>
          <Button variant="ghost" onClick={onRefresh}>
            Refresh
          </Button>
        </div>
      </header>

      <section className="section">
        <Card title="Documents" hint={active.length > 0 ? `${active.length} still processing` : "All documents settled"}>
          {documents.error && documents.value === null ? (
            <ErrorState error={asError(documents.error)} title="Could not load documents" onRetry={onRefresh} />
          ) : list.length === 0 ? (
            documents.value === null ? (
              <p className="text-muted" style={{ marginBottom: 0 }}>
                <Spinner label="Loading documents" /> Loading documents and their pipeline state…
              </p>
            ) : (
              <EmptyState title="Nothing to process yet">
                Upload a document on the Document workspace screen and it appears here immediately with live stage
                progress.
              </EmptyState>
            )
          ) : (
            <div className="stack">
              {list.map((document) => (
                <div key={document.id} className="card card--tight">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div style={{ minWidth: 0 }}>
                      <p style={{ margin: 0, fontWeight: 600, overflowWrap: "anywhere" }}>{document.filename}</p>
                      <p className="text-small text-dim" style={{ margin: 0 }}>
                        {document.extension.toUpperCase()} · {formatBytes(document.size_bytes)} · uploaded{" "}
                        {formatDateTime(document.created_at)}
                        {document.page_count !== null ? ` · ${document.page_count} pages` : ""} · {document.chunk_count}{" "}
                        chunks
                      </p>
                    </div>
                    <div className="row">
                      <StatusPill status={document.status} />
                      <Button size="small" onClick={() => navigate(`/processing/${document.id}`)}>
                        Inspect
                      </Button>
                    </div>
                  </div>
                  {document.status === "processing" || document.status === "queued" ? (
                    <div style={{ marginTop: "var(--space-3)" }}>
                      <ProgressBar
                        indeterminate
                        value={0}
                        label={statusLabel(document.status)}
                        detail="Open the document for exact stage progress"
                      />
                    </div>
                  ) : null}
                  {document.error ? (
                    <p className="text-small" style={{ color: "var(--rose)", marginBottom: 0 }}>
                      {document.error}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}

function ProcessingDetail({ documentId }: { documentId: string }) {
  const navigate = useNavigate();
  const { api, pushToast } = useApp();

  const status = usePolling<DocumentStatusResponse>(() => api.getDocumentStatus(documentId), {
    intervalMs: 900,
    maxIntervalMs: 5000,
    stopWhen: (value) => value.status === "ready" || value.status === "failed",
  });

  const detail = useAsync(() => api.getDocument(documentId), [api, documentId]);

  const current = status.value;
  const isReady = current?.status === "ready" || detail.data?.indexed === true;

  const sources = useAsync<SourceResponse>(() => api.getDocumentSources(documentId), [api, documentId], {
    enabled: isReady,
  });

  const retry = useMutation(() => api.retryDocument(documentId), {
    onSuccess: () => {
      pushToast({
        tone: "success",
        title: "Reprocessing started",
        message: "The pipeline is running again from the validation stage.",
      });
      detail.reload();
    },
  });

  const document = detail.data;
  const progress = current?.progress ?? 0;
  const chunks: Citation[] = sources.data?.sources ?? [];

  if (status.error && !current) {
    return (
      <div className="main__inner">
        <ErrorState
          error={asError(status.error)}
          title="Could not read this document's status"
          onRetry={() => status.error && window.location.reload()}
        />
        <div className="row">
          <Button onClick={() => navigate("/processing")}>Back to the pipeline list</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <Link to="/processing">Processing pipeline</Link>
        <span className="breadcrumbs__sep">/</span>
        <span>{document?.filename ?? documentId}</span>
      </div>

      <header className="page-header">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ overflowWrap: "anywhere" }}>{document?.filename ?? "Loading document…"}</h1>
            <p className="page-header__lede" style={{ marginBottom: "var(--space-2)" }}>
              Live stage-by-stage progress for document <span className="mono">{documentId}</span>.
            </p>
            {current ? (
              <div className="row">
                <StatusPill status={current.status} />
                {current.indexed ? <span className="pill pill--ready">Indexed</span> : null}
                <span className="pill">{Math.round(progress * 100)}% complete</span>
                {current.retryable ? <span className="pill pill--queued">Retry available</span> : null}
              </div>
            ) : null}
          </div>
          <div className="row row--end">
            <Button variant="ghost" onClick={detail.reload}>
              Refresh details
            </Button>
            {current?.retryable ? (
              <Button
                variant="primary"
                loading={retry.pending}
                loadingLabel="Restarting…"
                onClick={() => void retry.run()}
              >
                Retry processing
              </Button>
            ) : null}
            <Button
              onClick={() => navigate(`/chat?docs=${encodeURIComponent(documentId)}`)}
              disabled={!isReady}
            >
              Ask about it
            </Button>
          </div>
        </div>
      </header>

      {retry.error ? (
        <section className="section">
          <ErrorState error={retry.error} title="Retry failed" />
        </section>
      ) : null}

      {current?.error ? (
        <section className="section">
          <Card title="Processing failed" accent>
            <p style={{ marginBottom: 0 }}>{current.error}</p>
          </Card>
        </section>
      ) : null}

      <section className="section">
        <Card title="Progress">
          <div className="row" style={{ alignItems: "center", gap: "var(--space-5)" }}>
            <OrbitVisual state={current?.status ?? "queued"} />
            <div style={{ flex: "1 1 320px", minWidth: 260 }}>
              <ProgressBar
                value={progress}
                label={current ? statusLabel(current.status) : "Waiting for status…"}
                detail={current ? `${Math.round(progress * 100)}%` : "No status response yet"}
              />
              {current?.status === "ready" ? (
                <p className="text-small text-muted" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                  Indexing finished: chunks were embedded, written to the persistent vector index and then re-read to
                  verify they are retrievable.
                </p>
              ) : current?.status === "failed" ? (
                <p className="text-small text-muted" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                  The pipeline stopped at the first failing stage. The message above is the unmodified extractor error.
                </p>
              ) : (
                <p className="text-small text-muted" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                  {current
                    ? "This screen polls the backend about once a second and stops as soon as indexing settles."
                    : "Waiting for the first status response. Polling pauses while this tab is in the background and resumes when it is visible again."}
                </p>
              )}
            </div>
          </div>
        </Card>
      </section>

      <section className="section" aria-labelledby="stages-heading">
        <Card
          title="Pipeline stages"
          titleId="stages-heading"
          hint="Each line corresponds to a row in the local SQLite database."
        >
          <StageTimeline stages={current?.stages ?? document?.stages ?? []} />
        </Card>
      </section>

      <section className="section">
        <Card title="Extracted content">
          {document ? (
            <div className="grid grid--4">
              <Metric
                label="Characters"
                value={document.char_count.toLocaleString()}
                note="After extraction and cleanup"
              />
              <Metric label="Pages" value={document.page_count ?? "—"} note="Available for PDFs" />
              <Metric label="Chunks indexed" value={document.chunk_count} note="Retrievable passages" />
              <Metric
                label="Embedding"
                value={document.embedding_provider}
                note={`${document.embedding_dim} dimensions`}
              />
            </div>
          ) : detail.loading ? (
            <p className="text-muted">Loading document metadata…</p>
          ) : detail.error ? (
            <ErrorState error={detail.error} title="Could not load document metadata" onRetry={detail.reload} />
          ) : null}
        </Card>
      </section>

      <section className="section">
        <Card title="Indexed chunks" hint="Up to 50 retrievable passages for this document, exactly as stored.">
          {!isReady ? (
            <Notice>Chunks appear once indexing completes.</Notice>
          ) : sources.loading ? (
            <p className="text-muted">Loading chunks…</p>
          ) : sources.error ? (
            <ErrorState error={sources.error} title="Could not load chunks" onRetry={sources.reload} />
          ) : chunks.length === 0 ? (
            <EmptyState title="No chunks were produced">
              The extractor returned no usable text. Check the extract stage detail above.
            </EmptyState>
          ) : (
            <div className="stack">
              {chunks.map((chunk) => (
                <details key={chunk.chunk_id} className="card card--tight">
                  <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                    Chunk {chunk.index} · {chunk.page !== null ? `page ${chunk.page}` : "no page"} · chars{" "}
                    {chunk.char_start}–{chunk.char_end}
                  </summary>
                  <p className="citation__excerpt" style={{ marginTop: "var(--space-3)" }}>
                    {chunk.excerpt}
                  </p>
                  <p className="text-small text-dim mono" style={{ marginBottom: 0 }}>
                    chunk id {chunk.chunk_id}
                  </p>
                </details>
              ))}
            </div>
          )}
        </Card>
      </section>

      <section className="section">
        <Card title="Stage timings">
          {current && current.stages.length > 0 ? (
            <ul className="hint-list">
              {current.stages.map((stage) => {
                const millis =
                  stage.started_at && stage.finished_at
                    ? new Date(stage.finished_at).getTime() - new Date(stage.started_at).getTime()
                    : null;
                return (
                  <li key={stage.name}>
                    <span className="mono">{stage.name}</span> —{" "}
                    {millis === null ? "not finished yet" : formatMilliseconds(millis)}
                    {stage.detail ? ` · ${stage.detail}` : ""}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted">Stage timings appear as the pipeline progresses.</p>
          )}
        </Card>
      </section>
    </div>
  );
}
