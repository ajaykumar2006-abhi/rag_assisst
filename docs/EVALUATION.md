# Evaluation

Everything on this page was **measured in this workspace**, not estimated. The raw
artefacts are archived in [`docs/evidence/`](evidence/):

| Artefact | What it is |
| --- | --- |
| [`eval-synthetic-galaxy.json`](evidence/eval-synthetic-galaxy.json) | Full machine-readable result file (`run_id` `eval_20261013T141732`) |
| [`eval-synthetic-galaxy.md`](evidence/eval-synthetic-galaxy.md) | The same run rendered as a report |
| [`evidence-gate.txt`](evidence/evidence-gate.txt) | Refusal-quality measurement (in-scope vs. out-of-scope) |
| [`e2e-check.txt`](evidence/e2e-check.txt) | Live end-to-end HTTP run |
| [`backend-pytest.txt`](evidence/backend-pytest.txt) | Backend test suite output |
| [`frontend-checks.txt`](evidence/frontend-checks.txt) | Frontend typecheck, lint, unit tests, build |
| [`eval-neural-synthetic-galaxy.md`](evidence/eval-neural-synthetic-galaxy.md) | The same dataset re-run with the neural embedder (`run_id` `eval_20261015T060311`) |
| [`eval-neural-vs-hashing.md`](evidence/eval-neural-vs-hashing.md) | Side-by-side provider comparison: metrics, latency, memory, dependency cost |
| [`evidence-gate-neural.txt`](evidence/evidence-gate-neural.txt) | Refusal battery re-measured with the neural embedder |

To reproduce the numbers in this document, see
[§8 Reproducing](#8-reproducing-the-numbers).

---

## 1. The dataset

`synthetic_galaxy` ([`eval/datasets/synthetic_galaxy.json`](../eval/datasets/synthetic_galaxy.json))
describes a fictional deep-space observatory mission in three documents:

| Document | Format used at ingest | Content |
| --- | --- | --- |
| Mission overview | `.txt` | Launch date, orbit, instruments, ground stations, cost |
| Instrument specifications | `.txt` | Apertures, detectors, thermal limits, downlink rate |
| Operations procedures | `.txt` | Safe mode, calibration, passes, anomaly review |

Each document is ingested through the **production pipeline** (`upload → extract →
structure → chunk → embed → index`) in an isolated data directory, so an evaluation run
never touches the user's own library. With the default chunking configuration the corpus
produces **8 chunks**.

**18 questions**, each declaring:

- `question` — the natural-language question,
- `expected_answer` — a human-readable reference answer (shown in the UI; *not* used as a
  metric),
- `document_ids` — which document(s) may contain the answer,
- `relevant_passages` — **one or more verbatim substrings of the source text**.

Ground truth by *verbatim substring* is the important design decision. It makes relevance
labels mechanical and auditable: a retrieved chunk is relevant if and only if it contains a
declared substring. No human judgement, no LLM-as-judge, nothing to argue about.

The dataset also carries the question of *scope*: a good RAG system must refuse when the
documents cannot support an answer. That behaviour is measured separately in
[§5](#5-refusal-quality-the-evidence-gate), because it is not a retrieval metric.

## 2. Metric definitions

| Metric | Definition | Why it is defined this way |
| --- | --- | --- |
| **Recall@k** | Share of a question's `relevant_passages` that appear inside at least one of the top-k chunks (passage coverage). | Measures whether the evidence was found at all. Capped at 1 by construction. |
| **Precision@k** | Share of the k returned slots that are relevant chunks. | Measures how much of the reader's attention is spent on noise. Computed over the *requested* k, so it falls mechanically as k rises. |
| **MRR** | Mean of `1 / rank` of the first relevant chunk. | Measures whether the best evidence is *first*, which is what an answer generator actually consumes. |
| **Citation hit rate** | Share of questions where at least one citation returned to the user contains a ground-truth substring. | This is the metric that ties retrieval to the *citable* output: an answer is only auditable if its citation points at the passage the fact came from. |
| **Answer rate** | Share of in-scope questions that were answered rather than refused. | Detects an over-cautious evidence gate. |
| **Mean / p95 answer latency** | Wall time around the answering call only. | The interactive cost the user feels per question. |

No accuracy percentage is reported for answer *quality*, because answer quality is
extractive here: the metric that matters is whether the quoted sentence contains the fact,
and that is exactly what "citation hit rate" measures.

## 3. Measured results

Run `eval_20261013T141732`, dataset `synthetic_galaxy`, k = 5, default configuration:

| Setting | Value |
| --- | --- |
| Embedder | `hashing-subword-v1`, 512 dimensions, semantic = false |
| Answer provider | `extractive` |
| Chunking | 900 characters / 150 overlap |
| Fusion | dense 0.65, lexical 0.35 |
| `min_relevance` | 0.05 |
| Corpus | 3 documents, 8 chunks |
| Wall time | 0.321 s |

| Metric | Value |
| --- | --- |
| Recall@5 | **1.000** |
| Precision@5 | **0.2444** |
| MRR | **1.000** |
| Citation hit rate | **1.000** |
| Answer rate | **1.000** |
| Mean answer latency | **3.5 ms** |
| p95 answer latency | **4.4 ms** |

Per-question results (all 18 questions, every one answered with a citation hit):

| # | Question | Recall | P@5 | RR | Citation hit | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | When did the Helios mission launch? | 1.00 | 0.20 | 1.00 | yes | 2.61 ms |
| 2 | What altitude and inclination is the observatory orbit? | 1.00 | 0.40 | 1.00 | yes | 3.36 ms |
| 3 | Aperture of the Wide Field Imager and megapixels | 1.00 | 0.20 | 1.00 | yes | 3.33 ms |
| 4 | Frequency range of the Low Frequency Spectrometer | 1.00 | 0.40 | 1.00 | yes | 4.02 ms |
| 5 | Absolute pointing accuracy of the Fine Guidance Sensor | 1.00 | 0.40 | 1.00 | yes | 3.17 ms |
| 6 | How much data the solid state recorder holds | 1.00 | 0.20 | 1.00 | yes | 4.35 ms |
| 7 | Automatic safe-mode entry conditions | 1.00 | 0.20 | 1.00 | yes | 3.27 ms |
| 8 | Downlink pass duration and frequency | 1.00 | 0.20 | 1.00 | yes | 3.23 ms |
| 9 | Calibration cadence and references | 1.00 | 0.20 | 1.00 | yes | 2.87 ms |
| 10 | Proprietary period before public release | 1.00 | 0.20 | 1.00 | yes | 2.71 ms |
| 11 | Primary science objective | 1.00 | 0.20 | 1.00 | yes | 4.00 ms |
| 12 | Total instrument mass and peak power | 1.00 | 0.20 | 1.00 | yes | 2.70 ms |
| 13 | Ground stations and the primary control centre | 1.00 | 0.20 | 1.00 | yes | 4.41 ms |
| 14 | What recovery from safe mode requires | 1.00 | 0.40 | 1.00 | yes | 4.36 ms |
| 15 | How far in advance the timeline is uploaded | 1.00 | 0.20 | 1.00 | yes | 4.31 ms |
| 16 | Limiting magnitude in a 900 second exposure | 1.00 | 0.20 | 1.00 | yes | 4.02 ms |
| 17 | Total mission cost through the prime phase | 1.00 | 0.20 | 1.00 | yes | 2.07 ms |
| 18 | Wide field detector operating temperature | 1.00 | 0.20 | 1.00 | yes | 3.36 ms |

## 4. Reading these numbers honestly

**Precision@5 = 0.2444 is not a defect and not a success.** Most questions declare exactly
one relevant passage, so of five returned chunks at most one can be relevant: the ceiling
for a single-passage question is 0.20. The observed average (0.244) is above that floor
only because four questions declare two passages. A precision figure over five slots is
dominated by the definition of `k`, which is why the report marks it as `k`-sensitive and
why recall/MRR/citation-hit are the metrics to read.

**Recall@5 = 1.000 does not mean "the system always finds the answer".** It means it found
a chunk containing a declared substring for all 18 questions *in this corpus*. The corpus is
synthetic, deliberately well-chunked and written in a consistent register. Real-world
accuracy is not claimed; see [§7 Limitations](#7-limitations).

**MRR = 1.000** means the first relevant chunk was ranked first every time. With 8 chunks in
total this is a weak signal: the search space is tiny. It would be misleading to quote it as
evidence of ranking quality at scale.

**Latency excludes ingestion.** 3.5 ms is the answering call only (embed query → fuse →
extract sentences). Indexing a document takes seconds and is reported separately on the
Processing screen.

## 5. Refusal quality (the evidence gate)

Retrieval metrics never tell you whether the system knows when to shut up. That is measured
separately by [`scripts/measure_evidence_gate.py`](../scripts/measure_evidence_gate.py),
which uploads the shipped fixtures plus a document containing a prompt-injection attempt,
then asks a labelled battery of questions. Raw output:
[`docs/evidence/evidence-gate.txt`](evidence/evidence-gate.txt).

| Category | Questions | Outcome |
| --- | --- | --- |
| In-scope ("positive") | 7 | **7/7 answered**, each containing its expected fact |
| Paraphrase | 2 | **2/2 answered** (answers found via shared question terms) |
| Out-of-scope | 5 | **5/5 refused** with `answer_mode=insufficient` and **zero citations** |

Summary: **9/9 in-scope answered, 5/5 out-of-scope refused.**

Representative refusals, quoted from the run:

> *"Searched 4 document(s) … Best match scored 0.151. The closest passage shares almost no
> wording with the question (vector similarity 0.094, keyword overlap 0.256), which is the
> signature of a question this document set does not cover."*

> *"No sentence in the retrieved passages shared meaningful vocabulary with the question.
> Closest match scored 0.081."*

A refusal returns no citations at all, so a refusal can never be mistaken for a weak answer.
The script exits non-zero if any out-of-scope question is answered or any in-scope question
is refused, which is how CI gates this behaviour.

The same battery was re-run against the neural embedder on 2026-10-15
([`evidence-gate-neural.txt`](evidence/evidence-gate-neural.txt)) with the **identical outcome**:
9/9 answered, 5/5 refused. The best out-of-scope match under neural vectors scored 0.127 fused,
still refused — the calibrated gates hold for unit-normalised MiniLM vectors without adjustment.

## 6. Embedding provider comparison (measured 2026-10-15)

The optional neural provider (`EMBEDDING_PROVIDER=sentence`,
`sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions) was installed and run through the
**same frozen dataset, protocol, and machine** minutes after the lexical baseline:

| Metric | `hashing` (default) | `sentence` (neural) |
| --- | --- | --- |
| Recall@5 / Precision@5 | 1.0000 / 0.2444 | 1.0000 / 0.2444 |
| MRR / citation hit / answer rate | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| Mean answer latency (p95) | **2.38 ms** (4.0 ms) | **19.14 ms** (22.1 ms) |
| Evidence gate | 9/9 answered, 5/5 refused | 9/9 answered, 5/5 refused |
| Backend worker working set | **~81 MB** | **~556 MB** |
| Cold start | ~0 s | ~52 s (model load from cache) |
| Dependency cost | none | torch + sentence-transformers (~2 GB), ~90 MB model download |

Read honestly: **the two providers are tied on quality here, and this dataset cannot separate
them.** Its questions share vocabulary with the documents — exactly where a lexical embedder is
strong — so a tie is not evidence of equivalence in general. The neural provider's expected
advantage (paraphrases and synonyms with no shared vocabulary) was not measurable on this
corpus; its costs were measured and are real. The default therefore stays `hashing` on measured
cost, not on any claim of measured quality superiority. Full protocol, exact commands and
caveats: [docs/evidence/eval-neural-vs-hashing.md](evidence/eval-neural-vs-hashing.md).

## 7. Limitations

These are reproduced from the result file itself, because they are part of the measurement:

1. The dataset is **synthetic and small**; the numbers are specific to this dataset and
   configuration.
2. Ground truth is **substring containment**, which is exact but shallow: a chunk can be
   topically relevant and still be marked irrelevant if it paraphrases the source.
3. **Precision@k is computed against the requested k**, so a larger k mechanically lowers it.
4. **No comparison with any commercial system was run**, so no comparative claim is made.
5. Retrieval quality for the default `hashing` embedder is **lexical, not neural**. The
   optional `sentence` provider was measured on this dataset on 2026-10-15 and **tied** it
   ([§6](#6-embedding-provider-comparison-measured-2026-10-15)); its paraphrase advantage
   remains unmeasured because this corpus cannot expose it.

Two further caveats that come from the design rather than the dataset:

- **The paraphrase probes are few (2).** They pass because the questions share surface terms
  with the source ("send its data back", "main telescope mirror"). A paraphrase with no
  vocabulary overlap would fail against the hashing embedder — that is the honest boundary
  of a lexical vector space.
- **`min_relevance` and the structural support rule are calibrated on this corpus.** They are
  the mechanism behind the 5/5 refusals above. On a corpus with different term distributions
  they should be re-measured with `scripts/measure_evidence_gate.py` before being trusted.

## 8. Reproducing the numbers

```powershell
# 1. Start the backend (isolated data dir keeps your own library clean)
cd backend
$env:DATA_DIR = "./.eval-data"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# 2. In a second terminal, run the dataset through the API
curl.exe -X POST http://127.0.0.1:8010/api/v1/evaluation/run `
  -H "Content-Type: application/json" -d '{\"dataset\":\"synthetic_galaxy\"}'

# 3. The refusal measurement
python scripts\measure_evidence_gate.py --base-url http://127.0.0.1:8010

# 4. Optional — repeat 2 and 3 with the neural embedder
#    (one-time: pip install sentence-transformers; downloads a ~90 MB model)
$env:EMBEDDING_PROVIDER = "sentence"     # then restart the backend on a fresh port
```

The run is also available from the Evaluation screen, and every run is stored in SQLite and
listed by `GET /api/v1/evaluation/runs`. Result files are written to `eval/results/`
(git-ignored, since they are regenerated on demand); the run quoted above is archived in
[`docs/evidence/`](evidence/) so the numbers in this document stay checkable.
