# Testing

Four suites, in increasing order of realism. Every number quoted in the project README (delivered
separately) and in BUILD_PROGRESS comes from a run of these commands in this workspace.

## 1. Backend tests — `197 passed`

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest          # add -q for the short form
```

Isolation: `tests/conftest.py` injects a `ServiceContainer` pointed at a pytest `tmp_path`
onto `app.state`, so nothing touches the real `backend/data` directory and no test needs
network access or an API key.

| File | Covers |
| --- | --- |
| `test_extraction.py` | PDF page attribution, TXT encoding detection (UTF-8/UTF-16/CP1252), DOCX paragraphs + tables, scrambled-byte rejection, page and character ceilings |
| `test_chunking.py` | sentence-aware windows, overlap correctness, offset and page metadata, ordinal continuity, degenerate inputs |
| `test_text_utils.py` | tokenisation, stopwords, sentence splitting with abbreviations, keyword overlap, truncation |
| `test_embeddings_and_index.py` | determinism of the hashing embedder, unit-norm output, dimension guards, index persistence across reopen, manifest invalidation on embedder change, id-prefix deletion |
| `test_retrieval.py` | BM25 scoring and saturation, dense/lexical fusion weights, document scoping, tie-breaking, citation construction |
| `test_answering.py` | excerpt anchoring (containment, quoted-sentence preference, length caps), extractive filtering of weak sentences, duplicate suppression, verbatim-only output, citation-index/marker alignment, refusal paths |
| `test_pipeline.py` | all seven stages reached, stage detail text, retry, failure surfacing, progress computation |
| `test_api_qa.py` | evidence gate, no-citation-on-refusal, conversation recording, conversation-context retrieval retry (a vague in-conversation follow-up widens retrieval; an out-of-scope follow-up stays refused), multi-document scope |
| `test_api_documents.py` | upload/list/inspect/status/sources/delete/retry, unsupported type, oversize, content sniffing, 404s |
| `test_api_settings_and_evaluation.py` | settings read/patch, restart-required rejection, threshold behaviour, evaluation run persistence |
| `test_security.py` | path traversal filenames, oversized uploads, page ceilings, prompt-injection text treated as data, no temporary files left behind |
| `test_evaluation_service.py` | dataset loading, metric computation, isolated collection, report artefacts |

## 2. Frontend unit tests — `72 passed`

```powershell
cd frontend
npm test
```

jsdom + Testing Library. `tests/setup.ts` polyfills `matchMedia`, `scrollIntoView` and
`localStorage`, and cleans up between tests.

| Area | Covers |
| --- | --- |
| `format.test.ts` | byte/percent/duration/uptime formatting, relative timestamps, `[n]` marker parsing (multi-digit, bracketed words ignored), labels |
| `client.test.ts` | success parsing, backend error envelope surfaced verbatim, 5xx retryable vs 4xx not, network failure, timeout abort, non-JSON body, JSON body serialisation, multipart without a content type, 204 handling |
| `scope.test.ts` | which documents a question searches (empty selection, non-ready ids dropped, single-document route, "everything ready" collapsing to no filter) |
| `hooks.test.tsx` | `useAsync` loading/error/disabled, `useMutation` result/pending/double-submit guard, `usePolling` repeat, stop condition, error backoff, and the rule that a hidden tab still makes its first request |
| `components.test.tsx` | Nova moods and bubble, dropzone accept/reject with reasons, table sorting/labels/empty state/select-all, stage timeline durations, citation card scoring, toast roles and retry |
| `pages.test.tsx` | Welcome screen composed against a stubbed API surface: live health facts, document counts, unreachable backend, failed document list |
| `chat.test.tsx` | Ask-screen question flow: copy-answer, starting a new conversation without deleting stored history, failed question showing a single error with a working retry, and no duplicate page-level error banner |

Deliberately not covered by unit tests: visual layout and animation timing.

## 3. Live end-to-end — `59/59 checks`

```powershell
# terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --port 8000
# terminal 2
python scripts\make_sample_documents.py     # real PDF/TXT/DOCX fixtures
python scripts\e2e_check.py                 # exits non-zero on any failure
```

Against a running server over real HTTP: health, uploads of three real formats, all seven
stages completing, chunk production, five known-answer questions with fact and filename
assertions, PDF page numbers present, every `[n]` marker resolving to a returned citation,
an out-of-scope question refused with no citations, conversation persistence with citations,
and deletion removing the file, its vectors and its listing.

## 4. Evidence gate measurement — `9/9` answered, `5/5` refused

```powershell
python scripts\measure_evidence_gate.py
```

A labelled battery of in-scope, paraphrase and out-of-scope questions, printing the fused,
dense and lexical score of the best passage for each, the decision taken, and the reason the
backend reported. It writes `eval/results/evidence_gate_<timestamp>.json` and exits non-zero
if any out-of-scope question was answered or any in-scope question was refused. The
thresholds in `app/services/qa.py` are documented from this output.

## 5. Browser end-to-end — `7 passed`

Re-run against the final tree on 2026-10-15: `7 passed (50.0s)`, console evidence in
[`evidence/browser-e2e.txt`](evidence/browser-e2e.txt). A hand-driven session covering the
same six screens — including what the automated suite cannot show, such as dialog focus
behaviour and the fixes listed in [BUILD_PROGRESS.md](../BUILD_PROGRESS.md) — is recorded in
[`evidence/browser-walkthrough.md`](evidence/browser-walkthrough.md).

```powershell
cd frontend
npx playwright install chromium    # once
npm run test:e2e                   # needs backend :8000 and the dev server :5173
```

Chromium driving the real UI against the real backend, no API mocking: welcome screen facts,
upload → processing stages → ask → citation shown with page number → source viewer opens and
closes on Escape, refusal of an unsupported question, a real evaluation run rendering its six
measured metrics, settings storage report and the animation toggle persisting across reload,
deletion removing the row, and navigation across all six screens. The suite clears the
library in `beforeAll` so repeated runs are deterministic.

## 6. Static checks and build

```powershell
cd frontend
npm run typecheck     # tsc --noEmit, strict + noUncheckedIndexedAccess
npm run lint          # eslint 9 flat config, --max-warnings 0
npm run build         # tsc --noEmit && vite build
```

TypeScript is strict (`strict`, `noUnusedLocals`, `noUnusedParameters`,
`noUncheckedIndexedAccess`), and lint runs with zero warnings tolerated.

## What is not covered

- **The optional `sentence` embedding provider** — exercised live on 2026-10-15 (install,
  model download, evaluation run and evidence-gate battery; see
  [evidence/eval-neural-vs-hashing.md](evidence/eval-neural-vs-hashing.md)). Its failure paths
  remain unit-tested with injected failures; the two provider-specific failure modes not covered
  are a corrupted model cache and a Hugging Face outage mid-download.
- **The optional OpenAI-compatible answer provider** — needs an API key; unit-tested for
  configuration errors and refusal to start unconfigured, never called live.
- **Multi-user or concurrent-load behaviour** — the app is single-user by design.
- **Very large corpora** (tens of thousands of chunks): retrieval is exact search, and its
  scaling has not been benchmarked beyond laptop-scale collections.
