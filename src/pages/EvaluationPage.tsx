import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Metric } from "@/components/ui/Card";
import { EmptyState, ErrorState, Notice, BulletList } from "@/components/ui/Feedback";
import { NumberField, SelectField } from "@/components/ui/Field";
import { ProgressBar } from "@/components/ui/Pill";
import { useApp } from "@/context/AppContext";
import { useAsync } from "@/hooks/useAsync";
import { useMutation } from "@/hooks/useMutation";
import { formatDateTime, formatMetric, formatMilliseconds, formatPercent } from "@/services/format";
import type { EvaluationRunResponse } from "@/types/api";

function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

/**
 * Screen 5 — the evaluation dashboard.
 *
 * Two kinds of number appear here and they are labelled differently on purpose:
 *   - *live* statistics (documents, chunks, latency) read from the running
 *     application's own database;
 *   - *measured* retrieval metrics produced by actually executing the evaluation
 *     dataset against the real pipeline.
 *
 * If no run has been performed the dashboard says so. It never displays an
 * invented score.
 */
export function EvaluationPage() {
  const { api, pushToast } = useApp();
  const [dataset, setDataset] = useState<string>("");
  const [topK, setTopK] = useState(5);
  const [limit, setLimit] = useState(0);
  const [runsRefresh, setRunsRefresh] = useState(0);

  const summary = useAsync(() => api.getEvaluationSummary(), [api]);
  const datasets = useAsync(() => api.listDatasets(), [api]);
  const runs = useAsync(() => api.listEvaluationRuns(), [api, runsRefresh]);

  const available = datasets.data ?? [];
  const selectedDataset = dataset || available[0] || "";

  const run = useMutation<EvaluationRunResponse, void>(
    () =>
      api.runEvaluation({
        dataset: selectedDataset || null,
        top_k: topK,
        limit: limit > 0 ? limit : null,
      }),
    {
      onSuccess: (result) => {
        setRunsRefresh((value) => value + 1);
        pushToast({
          tone: "success",
          title: "Evaluation run finished",
          message: `${result.sample_count} questions measured on "${result.dataset}" at k=${result.top_k}.`,
        });
      },
    },
  );

  const result = run.data;
  const live = summary.data;

  return (
    <div className="main__inner">
      <div className="breadcrumbs">
        <span>Screen 05</span>
        <span className="breadcrumbs__sep">/</span>
        <span>Evaluation</span>
      </div>

      <header className="page-header">
        <h1>Evaluation</h1>
        <p className="page-header__lede">
          Retrieval quality is measured, not asserted. Runs execute the synthetic dataset through the same extraction,
          chunking, embedding and retrieval code the chat screen uses, and record recall, precision, mean reciprocal rank
          and citation hit rate.
        </p>
      </header>

      <section className="section">
        <Card title="Live application statistics" hint="Read from this instance's SQLite event log and index.">
          {summary.error && !live ? (
            <ErrorState error={asError(summary.error)} title="Could not read live statistics" onRetry={summary.reload} />
          ) : live ? (
            <>
              <div className="grid grid--4">
                <Metric label="Documents" value={live.documents_total} note={`${live.documents_ready} ready`} />
                <Metric label="Chunks indexed" value={live.chunks_indexed} />
                <Metric label="Questions answered" value={live.questions_answered} note="Since the backend started" />
                <Metric
                  label="Mean answer latency"
                  value={formatMilliseconds(live.mean_answer_latency_ms)}
                  note={`p95 ${formatMilliseconds(live.p95_answer_latency_ms)}`}
                />
              </div>
              <ul className="hint-list" style={{ marginTop: "var(--space-4)" }}>
                <li>
                  Failed documents: <span className="mono">{live.documents_failed}</span> · processing errors logged:{" "}
                  <span className="mono">{live.errors_total}</span>
                </li>
                <li>
                  Embedding provider: <span className="mono">{live.embedding_provider}</span>
                </li>
                <li>
                  Answer provider: <span className="mono">{live.answer_provider}</span>
                </li>
              </ul>
            </>
          ) : (
            <p className="text-muted">Loading live statistics…</p>
          )}
        </Card>
      </section>

      <section className="section">
        <Card title="Run an evaluation" hint="Runs against an isolated evaluation collection; your own documents are untouched.">
          <div className="grid grid--3">
            <SelectField
              label="Dataset"
              value={selectedDataset}
              onChange={(event) => setDataset(event.target.value)}
              hint="JSON files found in eval/datasets"
              options={
                available.length > 0
                  ? available.map((name) => ({ value: name, label: name }))
                  : [{ value: "", label: datasets.loading ? "Loading…" : "No datasets found" }]
              }
              disabled={available.length === 0}
            />
            <NumberField
              label="Retrieve top k"
              value={topK}
              min={1}
              max={20}
              onValueChange={setTopK}
              hint="Chunks retrieved per question"
            />
            <NumberField
              label="Limit questions"
              value={limit}
              min={0}
              max={500}
              onValueChange={setLimit}
              hint="0 means every question in the dataset"
            />
          </div>
          <div className="row" style={{ marginTop: "var(--space-4)" }}>
            <Button
              variant="primary"
              loading={run.pending}
              loadingLabel="Running the dataset…"
              onClick={() => void run.run()}
              disabled={available.length === 0}
            >
              Run evaluation now
            </Button>
            <span className="text-small text-dim">
              {datasets.error
                ? `Could not list datasets: ${asError(datasets.error).message}`
                : `${available.length} dataset${available.length === 1 ? "" : "s"} available`}
            </span>
          </div>
          {run.pending ? (
            <div style={{ marginTop: "var(--space-4)" }}>
              <ProgressBar indeterminate label="Extracting, chunking, embedding and scoring every question" />
            </div>
          ) : null}
          {run.error ? (
            <div style={{ marginTop: "var(--space-4)" }}>
              <ErrorState error={run.error} title="The evaluation run failed" />
            </div>
          ) : null}
        </Card>
      </section>

      {result ? (
        <>
          <section className="section">
            <Card
              title={`Measured results · ${result.dataset}`}
              hint={`${result.sample_count} questions at k=${result.top_k}, recorded ${formatDateTime(result.created_at)}`}
            >
              <div className="grid grid--3">
                <Metric
                  label={`Recall@${result.top_k}`}
                  value={formatPercent(result.recall_at_k, 1)}
                  note="Share of questions whose gold chunk was retrieved"
                />
                <Metric
                  label={`Precision@${result.top_k}`}
                  value={formatPercent(result.precision_at_k, 1)}
                  note="Share of retrieved chunks that were relevant"
                />
                <Metric label="MRR" value={formatMetric(result.mrr, 4)} note="Mean reciprocal rank of the first hit" />
                <Metric
                  label="Citation hit rate"
                  value={formatPercent(result.citation_hit_rate, 1)}
                  note="Answers whose citations include the gold chunk"
                />
                <Metric
                  label="Answer rate"
                  value={formatPercent(result.answer_rate, 1)}
                  note="Questions that produced an answer rather than a refusal"
                />
                <Metric
                  label="Mean latency"
                  value={formatMilliseconds(result.mean_latency_ms)}
                  note="Retrieval plus answer assembly per question"
                />
              </div>
              {result.result_path ? (
                <p className="text-small text-dim" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                  Detailed per-question results were written to <span className="mono">{result.result_path}</span>.
                </p>
              ) : null}
            </Card>
          </section>

          <section className="section">
            <Card title="Methodology">
              <p style={{ whiteSpace: "pre-wrap" }}>{result.methodology}</p>
              <BulletList label="Known limitations" items={result.limitations} />
            </Card>
          </section>

          <section className="section">
            <Card title="Per-question results" hint="Every row is a question that was actually executed.">
              <div className="table-scroll">
                <table className="doc-table">
                  <caption>
                    Retrieval and answering outcome for each evaluated question. Recall uses chunk-level ground truth.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Question</th>
                      <th scope="col">Answer mode</th>
                      <th scope="col">Recall@k</th>
                      <th scope="col">Precision@k</th>
                      <th scope="col">RR</th>
                      <th scope="col">Cited</th>
                      <th scope="col">Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.cases.map((item, index) => (
                      <tr key={item.id}>
                        <td className="mono">{index + 1}</td>
                        <td>
                          <div style={{ overflowWrap: "anywhere" }}>{item.question}</div>
                          <div className="text-small text-dim">expected: {item.expected_answer}</div>
                        </td>
                        <td>
                          <span className={`pill pill--${item.answer_mode}`}>{item.answer_mode}</span>
                        </td>
                        <td className="mono">{item.recall_at_k.toFixed(2)}</td>
                        <td className="mono">{item.precision_at_k.toFixed(2)}</td>
                        <td className="mono">{item.reciprocal_rank.toFixed(2)}</td>
                        <td>{item.citation_hit ? "yes" : "no"}</td>
                        <td className="mono">{Math.round(item.latency_ms)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </section>
        </>
      ) : (
        <section className="section">
          <Card title="No run recorded in this session">
            <EmptyState title="Run the evaluation to see measured numbers">
              The dashboard will not show placeholder metrics. Press &quot;Run evaluation now&quot; above — the synthetic
              dataset is indexed in an isolated store, so your own documents are never modified.
            </EmptyState>
          </Card>
        </section>
      )}

      <section className="section">
        <Card title="Recorded runs" hint="Persisted in the local database, newest first.">
          {runs.error && !runs.data ? (
            <ErrorState
              error={asError(runs.error)}
              title="Could not load recorded runs"
              onRetry={() => setRunsRefresh((value) => value + 1)}
            />
          ) : runs.data && runs.data.runs.length > 0 ? (
            <div className="table-scroll">
              <table className="doc-table">
                <caption>Every evaluation run this installation has recorded.</caption>
                <thead>
                  <tr>
                    <th scope="col">Run</th>
                    <th scope="col">Dataset</th>
                    <th scope="col">Questions</th>
                    <th scope="col">k</th>
                    <th scope="col">Recall@k</th>
                    <th scope="col">MRR</th>
                    <th scope="col">When</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.runs.map((record) => (
                    <tr key={record.run_id}>
                      <td className="mono" style={{ fontSize: "0.74rem" }}>
                        {record.run_id}
                      </td>
                      <td>{record.dataset}</td>
                      <td className="mono">{record.sample_count}</td>
                      <td className="mono">{record.top_k}</td>
                      <td className="mono">{formatMetric(record.metrics["recall_at_k"] ?? Number.NaN, 4)}</td>
                      <td className="mono">{formatMetric(record.metrics["mrr"] ?? Number.NaN, 4)}</td>
                      <td className="text-small text-muted">{formatDateTime(record.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Notice>No runs recorded yet. The first completed run will appear here.</Notice>
          )}
        </Card>
      </section>
    </div>
  );
}
