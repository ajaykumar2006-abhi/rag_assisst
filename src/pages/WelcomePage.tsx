import { Link, useNavigate } from "react-router-dom";

import { Nova } from "@/components/Nova";
import { Button } from "@/components/ui/Button";
import { Card, Metric } from "@/components/ui/Card";
import { ErrorState, Notice } from "@/components/ui/Feedback";
import { useApp } from "@/context/AppContext";
import { useAsync } from "@/hooks/useAsync";
import { formatBytes, formatUptime, pluralize } from "@/services/format";

const PIPELINE_STEPS = [
  {
    title: "Extract",
    body: "PDF text layers page by page (pypdf), TXT with encoding detection, and DOCX paragraphs and tables (python-docx).",
  },
  {
    title: "Chunk",
    body: "Sentence-aware windows with configurable size and overlap, each carrying page and character offsets.",
  },
  {
    title: "Embed",
    body: "Every chunk is embedded locally — deterministic subword hashing by default, or a local sentence-transformers model.",
  },
  {
    title: "Index",
    body: "Vectors persist to a NumPy index on disk with a manifest recording the provider and dimension.",
  },
  {
    title: "Retrieve",
    body: "Dense cosine similarity blended with keyword overlap, then filtered by a minimum relevance floor.",
  },
  {
    title: "Answer",
    body: "Grounded extractive answers assembled only from retrieved passages, with a citation attached to every sentence.",
  },
];

/**
 * Screen 1 — the galaxy welcome page.
 *
 * Everything numeric on this page comes from the live API: the health probe and
 * the document list. If the backend is down the page says so instead of showing
 * invented statistics.
 */
export function WelcomePage() {
  const navigate = useNavigate();
  const { health, healthError, api } = useApp();
  const documents = useAsync(() => api.listDocuments(), [api]);

  const list = documents.data ?? [];
  const ready = list.filter((document) => document.status === "ready");
  const totalBytes = list.reduce((sum, document) => sum + document.size_bytes, 0);
  const totalChunks = list.reduce((sum, document) => sum + document.chunk_count, 0);

  return (
    <div className="main__inner">
      <section className="section" aria-labelledby="welcome-heading">
        <Card accent>
          <div className="row" style={{ alignItems: "center", gap: "var(--space-5)" }}>
            <div style={{ flex: "1 1 320px", minWidth: 280 }}>
              <p className="field__label" style={{ marginBottom: 6 }}>
                Screen 01 · Welcome
              </p>
              <h1 id="welcome-heading">Ask your own documents. Get answers you can check.</h1>
              <p className="page-header__lede">
                RAG Document Intelligence reads PDFs, text files and Word documents from this machine, builds a
                searchable vector index over them, and answers questions using only what it actually found — every
                sentence carries a citation back to the exact passage.
              </p>
              <div className="row" style={{ marginTop: "var(--space-4)" }}>
                <Button variant="primary" onClick={() => navigate("/documents")}>
                  Upload a document
                </Button>
                <Button variant="ghost" onClick={() => navigate("/chat")}>
                  Ask a question
                </Button>
              </div>
            </div>
            <div style={{ flex: "0 1 320px", display: "flex", justifyContent: "center" }}>
              <Nova
                mood={healthError ? "concerned" : health ? "happy" : "thinking"}
                size={150}
                message={
                  healthError
                    ? "I cannot reach the backend. Start it with the command in the README and I will reconnect automatically."
                    : health
                      ? `Systems ready. Embeddings running on ${health.embedding_provider}, answers produced by ${health.answer_provider}. I have ${health.documents_indexed} ${pluralize(health.documents_indexed, "document")} indexed.`
                      : "Checking on the backend…"
                }
              />
            </div>
          </div>
        </Card>
      </section>

      {healthError ? (
        <section className="section">
          <ErrorState
            error={healthError}
            title="The backend is not reachable"
            onRetry={() => window.location.reload()}
          />
          <Notice tone="warn">
            Start the API first: <span className="mono">uvicorn app.main:app --reload --port 8000</span> from the{" "}
            <span className="mono">backend</span> folder, then reload this page.
          </Notice>
        </section>
      ) : null}

      <section className="section" aria-labelledby="system-heading">
        <Card
          title="Live system state"
          titleId="system-heading"
          hint="Values below are read from the running backend, not hard-coded."
        >
          <div className="grid grid--4">
            <Metric
              label="Documents indexed"
              value={health ? health.documents_indexed : "—"}
              note="Chunks currently in the vector index"
            />
            <Metric label="Indexed chunks" value={totalChunks} note={documents.loading ? "Loading…" : "Across all documents"} />
            <Metric
              label="Ready documents"
              value={`${ready.length} / ${list.length}`}
              note="Ready documents can be questioned"
            />
            <Metric label="Stored locally" value={formatBytes(totalBytes)} note="Original uploads on disk" />
          </div>
          {health ? (
            <ul className="hint-list" style={{ marginTop: "var(--space-4)" }}>
              <li>
                Embedding provider: <span className="mono">{health.embedding_provider}</span> ({health.embedding_dim} dims)
              </li>
              <li>
                Answer provider: <span className="mono">{health.answer_provider}</span>
                {health.generative_available
                  ? " — a generation provider is configured."
                  : " — extractive answers only, no API key required."}
              </li>
              <li>
                Data directory: <span className="mono">{health.data_dir}</span>
              </li>
              <li>
                Uptime: <span className="mono">{formatUptime(health.uptime_seconds)}</span>
              </li>
            </ul>
          ) : null}
          {documents.error ? <ErrorState error={documents.error} title="Could not list documents" onRetry={documents.reload} /> : null}
        </Card>
      </section>

      <section className="section" aria-labelledby="pipeline-heading">
        <Card
          title="What happens to a document"
          titleId="pipeline-heading"
          hint="Seven stages, each reported live on the Processing screen."
        >
          <div className="grid grid--3">
            {PIPELINE_STEPS.map((step, index) => (
              <div key={step.title}>
                <p className="metric__label">
                  Stage {index + 1}
                </p>
                <h4 style={{ marginBottom: 4 }}>{step.title}</h4>
                <p className="text-muted text-small" style={{ margin: 0 }}>
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="section">
        <Card
          title="Six connected screens"
          hint="Everything below runs against the same backend and the same local data."
        >
          <ul className="hint-list">
            <li>
              <Link to="/documents">Document workspace</Link> — upload, inspect, delete, and select several documents at
              once.
            </li>
            <li>
              <Link to="/processing">Processing pipeline</Link> — real per-stage progress, extracted text statistics and
              retry on failure.
            </li>
            <li>
              <Link to="/chat">Ask</Link> — grounded answers with clickable citations and page references.
            </li>
            <li>
              <Link to="/evaluation">Evaluation</Link> — measured retrieval quality on a synthetic dataset, including
              its limitations.
            </li>
            <li>
              <Link to="/settings">Settings &amp; privacy</Link> — retrieval tuning, embedding provider, and everything
              stored on disk.
            </li>
          </ul>
        </Card>
      </section>
    </div>
  );
}
