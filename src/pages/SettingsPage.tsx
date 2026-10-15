import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Metric } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { BulletList, ErrorState, Notice } from "@/components/ui/Feedback";
import { NumberField, Toggle } from "@/components/ui/Field";
import { useApp } from "@/context/AppContext";
import { useAsync } from "@/hooks/useAsync";
import { useMutation } from "@/hooks/useMutation";
import { formatBytes } from "@/services/format";
import type { SettingsResponse, SettingsUpdate } from "@/types/api";

function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

interface Draft {
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  dense_weight: number;
  lexical_weight: number;
  min_relevance: number;
  answer_max_sentences: number;
}

function toDraft(settings: SettingsResponse): Draft {
  return {
    chunk_size: settings.chunk_size,
    chunk_overlap: settings.chunk_overlap,
    top_k: settings.top_k,
    dense_weight: settings.dense_weight,
    lexical_weight: settings.lexical_weight,
    min_relevance: settings.min_relevance,
    answer_max_sentences: settings.answer_max_sentences,
  };
}

/**
 * Screen 6 — settings and privacy.
 *
 * Retrieval and chunking values can be tuned here and take effect immediately for
 * new questions. Anything that would change the embedding space or the answer
 * backend (and therefore requires an index rebuild or a provider re-validation)
 * is shown as read-only with the exact environment variable to change, rather
 * than as a control that would silently do nothing.
 */
export function SettingsPage() {
  const { api, pushToast, motionEnabled, toggleMotion, systemReducedMotion } = useApp();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirmWipe, setConfirmWipe] = useState(false);

  const settings = useAsync(() => api.getSettings(), [api]);
  const privacy = useAsync(() => api.getPrivacy(), [api]);

  useEffect(() => {
    if (settings.data) setDraft(toDraft(settings.data));
  }, [settings.data]);

  const save = useMutation((patch: SettingsUpdate) => api.updateSettings(patch), {
    onSuccess: (response) => {
      setDraft(toDraft(response.settings));
      pushToast({
        tone: "success",
        title: "Settings applied",
        message: response.notice ?? "New values apply to questions asked from now on.",
      });
    },
    onError: (error) => {
      pushToast({ tone: "error", title: "Settings were not saved", message: error.message });
    },
  });

  const wipe = useMutation(() => api.deleteAllDocuments(), {
    onSuccess: (response) => {
      pushToast({
        tone: "success",
        title: "All documents deleted",
        message: `${response.documents_removed} document${response.documents_removed === 1 ? "" : "s"} and their vectors were removed.`,
      });
      setConfirmWipe(false);
      privacy.reload();
      settings.reload();
    },
    onError: (error) => pushToast({ tone: "error", title: "Deletion failed", message: error.message }),
  });

  const current = settings.data;

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((previous) => (previous ? { ...previous, [key]: value } : previous));
  }

  const dirty =
    draft !== null &&
    current !== null &&
    (draft.chunk_size !== current.chunk_size ||
      draft.chunk_overlap !== current.chunk_overlap ||
      draft.top_k !== current.top_k ||
      draft.dense_weight !== current.dense_weight ||
      draft.lexical_weight !== current.lexical_weight ||
      draft.min_relevance !== current.min_relevance ||
      draft.answer_max_sentences !== current.answer_max_sentences);

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <span>Screen 06</span>
        <span className="breadcrumbs__sep">/</span>
        <span>Settings &amp; privacy</span>
      </div>

      <header className="page-header">
        <h1>Settings &amp; privacy</h1>
        <p className="page-header__lede">
          Tune retrieval for your documents, see exactly which provider performs each step, and inspect or delete
          everything this application has written to disk.
        </p>
      </header>

      {settings.error && !current ? (
        <section className="section">
          <ErrorState error={asError(settings.error)} title="Could not load settings" onRetry={settings.reload} />
        </section>
      ) : null}

      <section className="section" aria-labelledby="retrieval-heading">
        <Card
          title="Retrieval and chunking"
          titleId="retrieval-heading"
          hint="Changes apply immediately to new questions and to documents indexed from now on."
          actions={
            <>
              <Button
                size="small"
                variant="ghost"
                disabled={!dirty}
                onClick={() => current && setDraft(toDraft(current))}
              >
                Reset
              </Button>
              <Button
                size="small"
                variant="primary"
                disabled={!dirty || !draft}
                loading={save.pending}
                loadingLabel="Saving…"
                onClick={() => draft && void save.run({ ...draft })}
              >
                Save changes
              </Button>
            </>
          }
        >
          {draft && current ? (
            <>
              {dirty ? <Notice>You have unsaved changes.</Notice> : null}
              <div className="grid grid--3" style={{ marginTop: dirty ? "var(--space-3)" : 0 }}>
                <NumberField
                  label="Chunk size (characters)"
                  value={draft.chunk_size}
                  min={200}
                  max={4000}
                  step={50}
                  onValueChange={(value) => update("chunk_size", value)}
                  hint="Documents are re-chunked only when re-uploaded"
                />
                <NumberField
                  label="Chunk overlap"
                  value={draft.chunk_overlap}
                  min={0}
                  max={Math.max(0, draft.chunk_size - 1)}
                  step={10}
                  onValueChange={(value) => update("chunk_overlap", value)}
                  hint="Must stay below the chunk size"
                />
                <NumberField
                  label="Default passages (top k)"
                  value={draft.top_k}
                  min={1}
                  max={20}
                  onValueChange={(value) => update("top_k", value)}
                  hint="Used when the Ask screen does not override it"
                />
                <NumberField
                  label="Dense weight"
                  value={draft.dense_weight}
                  min={0}
                  max={1}
                  step={0.05}
                  onValueChange={(value) => update("dense_weight", value)}
                  hint="Weight of vector similarity in the fused score"
                />
                <NumberField
                  label="Lexical weight"
                  value={draft.lexical_weight}
                  min={0}
                  max={1}
                  step={0.05}
                  onValueChange={(value) => update("lexical_weight", value)}
                  hint="Weight of keyword overlap in the fused score"
                />
                <NumberField
                  label="Minimum relevance"
                  value={draft.min_relevance}
                  min={0}
                  max={1}
                  step={0.01}
                  onValueChange={(value) => update("min_relevance", value)}
                  hint="Below this score the assistant refuses to answer"
                />
                <NumberField
                  label="Maximum answer sentences"
                  value={draft.answer_max_sentences}
                  min={1}
                  max={20}
                  onValueChange={(value) => update("answer_max_sentences", value)}
                  hint="Extractive answers are trimmed to this length"
                />
              </div>
              {save.error ? (
                <div style={{ marginTop: "var(--space-4)" }}>
                  <ErrorState error={save.error} title="The backend rejected these values" />
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-muted">Loading configuration…</p>
          )}
        </Card>
      </section>

      <section className="section">
        <Card title="Providers" hint="Set at startup from environment variables; changing them needs a restart.">
          {current ? (
            <>
              <div className="grid grid--3">
                <Metric
                  label="Embedding provider"
                  value={current.embedding_provider}
                  note={`${current.embedding_dim} dimensions · ${current.embedding_model}`}
                />
                <Metric label="Answer provider" value={current.answer_provider} note={current.answer_provider === "extractive" ? "Fully local, no API key" : "External service configured"} />
                <Metric
                  label="Answer provider ready"
                  value={current.answerer_available ? "yes" : "no"}
                  note={current.answerer_available ? "Can answer with the current configuration" : current.answerer_reason}
                />
                <Metric
                  label="Generation API key"
                  value={current.llm_configured ? "set" : "not set"}
                  note={
                    current.answer_provider === "extractive"
                      ? "Not needed: answers are extractive and local"
                      : current.llm_model
                        ? `Model ${current.llm_model}`
                        : "Set LLM_API_KEY and LLM_MODEL to use the external provider"
                  }
                />
              </div>
              <div className="grid grid--2" style={{ marginTop: "var(--space-4)" }}>
                <BulletList label="Runs locally on this machine" items={current.runs_locally} />
                <BulletList label="Requires an external service" items={current.requires_external_service} />
              </div>
              <Notice tone="warn">
                To change either provider, edit <span className="mono">EMBEDDING_PROVIDER</span> or{" "}
                <span className="mono">ANSWER_PROVIDER</span> in <span className="mono">.env</span> and restart the
                backend. Switching the embedding provider requires re-indexing your documents, because vectors from
                different models are not comparable — re-upload them afterwards.
              </Notice>
              <ul className="hint-list">
                <li>
                  Upload limits: <span className="mono">{current.max_upload_mb} MB</span> per file,{" "}
                  <span className="mono">{current.max_pages} pages</span> per document.
                </li>
                <li>
                  Accepted extensions: <span className="mono">{current.allowed_extensions.join(", ")}</span>
                </li>
                <li>
                  Allowed browser origins: <span className="mono">{current.cors_origins.join(", ")}</span>
                </li>
                <li>
                  Data directory: <span className="mono">{current.data_dir}</span>
                </li>
              </ul>
            </>
          ) : (
            <p className="text-muted">Provider details load with the configuration above.</p>
          )}
        </Card>
      </section>

      <section className="section">
        <Card title="Accessibility and motion">
          <Toggle
            checked={motionEnabled}
            onChange={() => toggleMotion()}
            label="Enable Galaxy animations"
            hint={
              systemReducedMotion
                ? "Your operating system asks for reduced motion, so animations started off. You can override that here."
                : "Star twinkle, nebula drift and Nova's float. Turn off for a completely static interface."
            }
          />
          <Notice>
            Focus outlines, the skip link, keyboard reachable controls, labelled inputs and live regions announcing upload
            progress and errors are always on and are not affected by this switch.
          </Notice>
        </Card>
      </section>

      <section className="section">
        <Card title="What is stored on this machine" hint="Measured from the filesystem, not estimated.">
          {privacy.error && !privacy.data ? (
            <ErrorState error={asError(privacy.error)} title="Could not read storage details" onRetry={privacy.reload} />
          ) : privacy.data ? (
            <>
              <div className="table-scroll">
                <table className="doc-table">
                  <caption>Every persistent artefact this application writes.</caption>
                  <thead>
                    <tr>
                      <th scope="col">Data</th>
                      <th scope="col">Location</th>
                      <th scope="col">Count</th>
                      <th scope="col">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {privacy.data.storage.map((entry) => (
                      <tr key={entry.what}>
                        <td>{entry.what}</td>
                        <td className="mono" style={{ overflowWrap: "anywhere" }}>
                          {entry.where}
                        </td>
                        <td className="mono">{entry.count.toLocaleString()}</td>
                        <td className="mono">{formatBytes(entry.bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-muted" style={{ marginTop: "var(--space-3)" }}>
                <strong>Retention:</strong> {privacy.data.retention}
              </p>
              <p className="text-muted">
                <strong>External services:</strong> {privacy.data.external_services}
              </p>
              <BulletList label="How to delete data" items={privacy.data.delete_instructions} />
            </>
          ) : (
            <p className="text-muted">Reading storage details…</p>
          )}
        </Card>
      </section>

      <section className="section">
        <Card title="Danger zone" accent>
          <p style={{ marginTop: 0 }}>
            Deleting every document removes the original files, all chunks and all vectors. Conversation history is
            cleared separately on the Ask screen. Neither action deletes the configuration or the application code.
          </p>
          <div className="row">
            <Button variant="danger" onClick={() => setConfirmWipe(true)}>
              Delete all documents and indexes
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                privacy.reload();
                settings.reload();
              }}
            >
              Refresh storage report
            </Button>
          </div>
          {wipe.error ? <ErrorState error={wipe.error} title="Deletion failed" /> : null}
        </Card>
      </section>

      <ConfirmDialog
        open={confirmWipe}
        title="Delete every document?"
        confirmLabel="Delete everything"
        danger
        pending={wipe.pending}
        onCancel={() => setConfirmWipe(false)}
        onConfirm={() => void wipe.run()}
      >
        <p style={{ marginTop: 0 }}>
          All uploaded files, their extracted chunks and the entire vector index will be deleted from{" "}
          <span className="mono">{current?.data_dir ?? "the data directory"}</span>.
        </p>
        <p style={{ marginBottom: 0 }}>This cannot be undone.</p>
      </ConfirmDialog>
    </div>
  );
}
