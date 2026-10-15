# Side-by-side embedding provider comparison — 2026-10-15

Same frozen dataset (`eval/datasets/synthetic_galaxy.json`, 18 questions, 3 synthetic
documents), same evaluation protocol (`POST /api/v1/evaluation/run`, top-k 5, default
fusion weights), same machine, minutes apart. This is the §7 comparison the project
deferred until the neural provider could actually be exercised.

## How it was run

```powershell
# Baseline (default lexical provider) — existing instance on :8000
curl -X POST http://127.0.0.1:8000/api/v1/evaluation/run -d '{"dataset":"synthetic_galaxy"}'
#   -> run eval_20261015T060243

# Neural provider — separate instance, fresh data directory, port 8001
cd backend
$env:DATA_DIR="...\backend\data-sentence-eval"; $env:EMBEDDING_PROVIDER="sentence"
.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8001
curl -X POST http://127.0.0.1:8001/api/v1/evaluation/run -d '{"dataset":"synthetic_galaxy"}'
#   -> run eval_20261015T060311

# Refusal quality against the neural instance
python scripts\\measure_evidence_gate.py --base-url http://127.0.0.1:8001
#   -> 9/9 in-scope answered, 5/5 out-of-scope refused (exit 0)
```

The neural instance required `pip install sentence-transformers` (installed 6.1.0 with
torch 2.14.1) and a one-time ~90 MB download of `sentence-transformers/all-MiniLM-L6-v2`
from Hugging Face. First model load took ~52 s from cache (plus ~100 s one-time torch
import on a cold process).

## Measured metrics

| Metric | hashing (default) | sentence (neural) |
| --- | --- | --- |
| Recall@5 | 1.0000 | 1.0000 |
| Precision@5 | 0.2444 | 0.2444 |
| MRR | 1.0000 | 1.0000 |
| Citation hit rate | 1.0000 | 1.0000 |
| Answer rate | 1.0000 | 1.0000 |
| Mean answer latency | **2.38 ms** | **19.14 ms** (~8x) |
| p95 answer latency | 4.4 ms (2026-10-13 run) | 22.1 ms |
| Evidence gate (answers / refusals) | 9/9, 5/5 | 9/9, 5/5 |
| Backend worker working set | **~81 MB** | **~556 MB** |
| Cold start (model load) | ~0 s | ~52 s (from cache) |
| Extra dependency | none | sentence-transformers + torch (~2 GB install, ~90 MB model download) |

Raw reports: [eval-synthetic-galaxy.md](eval-synthetic-galaxy.md) (hashing,
2026-10-13; identical metrics re-measured 2026-10-15 in run eval_20261015T060243),
[eval-neural-synthetic-galaxy.md](eval-neural-synthetic-galaxy.md) and
[evidence-gate-neural.txt](evidence-gate-neural.txt).

## Honest interpretation

- **On this dataset the two providers are tied on quality.** Both are perfect on
  recall, MRR, citation hit and answer rate, and both pass the refusal battery
  identically. The dataset is small and its questions share vocabulary with the
  documents, so it does not expose the paraphrase gap where a neural embedder should
  win. A tie here is *not* evidence that lexical retrieval is equally good in general;
  it is evidence that this dataset cannot separate them.
- **The neural provider's costs are measured and real:** ~8x answer latency on CPU,
  ~475 MB additional working memory, a ~2 GB dependency chain, a ~90 MB model download,
  and a ~52 s cold start.
- **Decision: hashing stays the default.** Not because it measured better — it did not —
  but because it measured *the same* on the frozen set at a fraction of the cost, and
  rule 7 forbids switching defaults on sound rather than measurement. Users who want
  paraphrase-resistant retrieval can set `EMBEDDING_PROVIDER=sentence`; the app reports
  the active provider on `/api/v1/health` and on the Welcome screen.
- The calibrated evidence-gate thresholds (`SUPPORT_DENSE_FLOOR = 0.12`,
  `SUPPORT_LEXICAL_FLOOR = 0.30` in `app/services/qa.py`) held for MiniLM's unit-norm
  vectors without adjustment — out-of-scope best matches scored at most 0.127 fused and
  were all refused.

## Limitations

- One run per provider, no repetitions; latency figures are single-run means on a
  busy laptop and will vary.
- 18 synthetic questions over 3 generated documents; substring ground truth. These
  numbers describe this dataset only and support no general or commercial comparison.
- The OpenAI-compatible answer provider was not exercised (no API key); the comparison
  above varies only the embedding provider with the extractive answerer fixed.
