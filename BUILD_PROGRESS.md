# Build progress — what is finished, what changed, what remains

Project: **RAG Document Intelligence — Galaxy Edition**
Folder: `C:\Users\<user>\Desktop\rag-document-intelligence`
Last verified: **2026-10-15**, on Windows with Python 3.13.5, Node 22.23.3, npm 10.9.9 — the full
suite was re-run that day after the Ask-screen and conversation-context work, with raw output in
[docs/evidence/backend-pytest.txt](docs/evidence/backend-pytest.txt),
[docs/evidence/frontend-checks.txt](docs/evidence/frontend-checks.txt),
[docs/evidence/e2e-check.txt](docs/evidence/e2e-check.txt),
[docs/evidence/evidence-gate.txt](docs/evidence/evidence-gate.txt) and
[docs/evidence/browser-e2e.txt](docs/evidence/browser-e2e.txt). That day also saw the optional
neural embedding provider installed and measured live for the first time
([docs/evidence/eval-neural-vs-hashing.md](docs/evidence/eval-neural-vs-hashing.md)).
(Originally verified 2026-10-13; re-verified 2026-10-14 in
[docs/evidence/reverification-20261014.md](docs/evidence/reverification-20261014.md).)

This file is the honest status ledger. Every number below was produced by a command run in this
workspace; the raw output is kept in [`docs/evidence/`](docs/evidence).

---

## 1. Status at a glance

| Area | State | Evidence |
| --- | --- | --- |
| Backend (FastAPI, 7-stage pipeline, SQLite + NumPy index) | **complete & verified** | [docs/evidence/backend-pytest.txt](docs/evidence/backend-pytest.txt) — `197 passed` |
| Frontend (React 18 + TS, six screens, hand-written CSS) | **complete & verified** | [docs/evidence/frontend-checks.txt](docs/evidence/frontend-checks.txt) — typecheck 0, lint 0, `72 passed`, build ok |
| Live end-to-end against a real server | **complete & verified** | [docs/evidence/e2e-check.txt](docs/evidence/e2e-check.txt) — `59/59 checks passed` |
| Evidence gate (answers vs. refusals) | **complete & verified** | [docs/evidence/evidence-gate.txt](docs/evidence/evidence-gate.txt) — `9/9` answered, `5/5` refused |
| Retrieval evaluation | **complete & verified** | [docs/evidence/eval-synthetic-galaxy.md](docs/evidence/eval-synthetic-galaxy.md) — recall@5 1.0000, MRR 1.0000 |
| Browser walkthrough of all six screens | **complete, with the caveat below** | [docs/evidence/browser-walkthrough.md](docs/evidence/browser-walkthrough.md) |
| GitHub Actions CI | **written, not yet executed on GitHub** | [.github/workflows/ci.yml](.github/workflows/ci.yml) |
| Optional neural embeddings (`EMBEDDING_PROVIDER=sentence`) | **implemented and measured live (2026-10-15)** | [docs/evidence/eval-neural-vs-hashing.md](docs/evidence/eval-neural-vs-hashing.md) — tied quality on the frozen dataset, 19.1 ms vs 2.4 ms latency, 556 MB vs 81 MB working set |
| Optional external answer provider (`ANSWER_PROVIDER=openai_compatible`) | **implemented, not exercised live** | unit tests only |
| OCR for scanned PDFs | **not implemented, by design** | see [docs/REFERENCE_AUDIT.md](docs/REFERENCE_AUDIT.md) |
| Deployment, auth, multi-user | **intentionally out of scope** | see [docs/SECURITY.md](docs/SECURITY.md) |

Nothing in the "complete" rows is simulated: no mocked API responses, no hard-coded metrics, no
placeholder modules. The two "not exercised" rows are real code paths with unit coverage that
were never run end to end, and they are reported as unverified in the project README's limitations list
(the README is delivered as a separate file at the requester's direction).

---

## 2. What was built

Nine weeks of work compressed into a build report would be useless; this is what is on disk now.

**Backend** (`backend/app/`)

- `api/` — `routes_health`, `routes_documents`, `routes_qa`, `routes_evaluation`, `routes_settings`, `deps`.
- `core/` — env-driven `config`, a typed error taxonomy with one error envelope, logging setup.
- `schemas/` — the Pydantic contract the frontend mirrors in `frontend/src/types/api.ts`.
- `services/` — `pipeline` (the seven stages), `extraction` (pypdf / python-docx / encoded text),
  `chunking`, `embeddings` (hashing + optional sentence-transformers), `retrieval` (dense + BM25
  fusion), `answering` (extractive + optional provider), `qa` (grounding and the evidence gate),
  `evaluation`, `container` (composition root).
- `storage/` — SQLite metadata and a persistent NumPy vector index with a manifest.

**Frontend** (`frontend/src/`)

- Six screens: `WelcomePage` (galaxy + Nova), `DocumentsPage`, `ProcessingPage`, `ChatPage`,
  `EvaluationPage`, `SettingsPage`.
- Components including `Nova`, `GalaxyBackground`, `DocumentTable`, `CitationCard`,
  `SourceViewer`, `ChatTranscript`, `ErrorBoundary` and `ui/*` primitives.
- Hooks `useAsync`, `usePolling`, `useMutation`, `useReducedMotion`; typed HTTP client with
  `ApiError`; `AppContext` for health, toasts and the persisted motion preference.
- One CSS file (~1,100 lines) with design tokens, animations, a `prefers-reduced-motion` path and
  an explicit "animations off" switch.

**Supporting material**

- Three real fixtures (`helios_mission_brief.pdf`, `helios_ops_procedures.docx`,
  `helios_instrument_specs.txt`) generated by `scripts/make_sample_documents.py`.
- `scripts/e2e_check.py` — 59 assertions against a live server, non-zero exit on any failure.
- `scripts/measure_evidence_gate.py` — the measurement behind the refusal thresholds.
- Synthetic dataset `eval/datasets/synthetic_galaxy.json` (18 questions, verbatim ground truth)
  whose stated limitations include the fact that the numbers describe *this* dataset only.
- Documentation: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
  [docs/API_CONTRACT.md](docs/API_CONTRACT.md), [docs/TESTING.md](docs/TESTING.md),
  [docs/SECURITY.md](docs/SECURITY.md), [docs/EVALUATION.md](docs/EVALUATION.md),
  [docs/REFERENCE_AUDIT.md](docs/REFERENCE_AUDIT.md).

---

## 3. Final verification run

Commands, in order, against the final tree.

```powershell
# 1. Backend tests — 197 passed
cd backend; .\.venv\Scripts\python.exe -m pytest

# 2. Frontend — typecheck, lint, unit tests, production build
cd frontend; npm run typecheck; npm run lint; npm test; npm run build   # 72 tests in 7 files

# 3. A real server on an empty data directory, then the live checks
#    (terminal 1) cd backend; $env:DATA_DIR="...\backend\data-verify"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
python scripts\e2e_check.py                # 59/59 checks passed
python scripts\measure_evidence_gate.py    # 9/9 answered, 5/5 refused
# 4. Evaluation through the API
curl -X POST .../api/v1/evaluation/run -d '{"dataset":"synthetic_galaxy"}'
#    recall@5 1.0000 · precision@5 0.2444 · MRR 1.0000 · citation hit 1.0000
#    answer rate 1.0000 · mean latency 3.5 ms
```

The live run used `DATA_DIR=backend/data-verify`, a directory that did not exist beforehand, so
the pipeline was exercised from an empty index. Vectors, chunks, files and the SQLite rows were
re-read from disk after a server restart, which is why the restart check could confirm
`documents_indexed = 1` again.

### Final measured numbers

| Metric | Final run (2026-10-15) |
| --- | --- |
| Backend tests | 197 passed |
| Frontend unit tests | 72 passed (7 files) |
| Live end-to-end checks | 59/59 passed |
| Evidence gate (default embedder) | 9/9 in-scope answered, 5/5 out-of-scope refused |
| Evidence gate (neural embedder) | 9/9 in-scope answered, 5/5 out-of-scope refused |
| Recall@5 / MRR / citation hit rate | 1.0000 / 1.0000 / 1.0000 (both providers) |
| Precision@5 | 0.2444 (low by construction — one relevant chunk among five slots) |
| Mean answer latency | 2.38 ms hashing (p95 4.0 ms) vs 19.1 ms neural (p95 22.1 ms) |
| Production bundle | 263.2 kB JS (81.9 kB gzip), 19.4 kB CSS (Midnight AI theme) |

---

## 4. Defects found by running the thing, and fixed

These were not found by reading code. Each was reproduced in a browser or by a script first.

1. **Chat blocked on an unrelated request.** The Ask screen disabled the question box until the
   document list had loaded, so a slow or failed list request made the whole screen unusable.
   Fixed: the question is accepted immediately; document-scope failures now surface as their own
   error.
2. **An in-flight answer was wiped by a conversation load.** Creating a conversation and then
   loading it raced, so the freshly streamed answer disappeared from the transcript. Fixed by
   sequencing the load against the in-flight answer.
3. **The Processing header claimed `Queued 0%` before any status response arrived.** An unfetched
   status was being displayed as a real one. It now reads `Waiting for status…` until the first
   response.
4. **Polling pages showed a false empty state in a background tab.** `usePolling` paused *all*
   ticks while the tab was hidden, including the first, so a page mounted in the background
   rendered "nothing to process yet" instead of its records. Fixed: the first request always
   runs; only the repeat ticks pause. Covered by a new unit test.
5. **Settings claimed an API key was configured when none existed.** The API field behind the
   label meant "the configured answerer can run", which is true of the local extractive answerer
   that needs no key. Split into `llm_configured` (a key is stored) and `answerer_available` (the
   answerer can run, with a reason when it cannot); two backend tests pin the distinction.
6. **The Welcome screen credited extraction to `pdfplumber`.** The project uses `pypdf`. Copy
   corrected.
7. **Follow-ups that rephrased an earlier question were refused.** A question like "and the second
   one?" shares no vocabulary with the document, so retrieval found nothing and the evidence gate
   refused it — correctly for a first question, wrongly inside a conversation that had already
   established the topic. Fixed in `app/services/qa.py`: when a question fails the gate inside a
   conversation, retrieval is retried once with the bounded prior questions of that conversation
   added to the query; the same gate judges the expanded retrieval and the answerer still scores
   sentences against the current question alone, so an out-of-scope follow-up stays refused
   (proven live and by three new backend tests).
8. **The Ask screen announced the same failure twice.** A failed question showed both a
   page-level error banner and an inline error on the message row. Fixed: the banner appears
   only when no failed message already carries the error.
9. **The Ask screen was missing three contract items** from its own spec — copy-answer, a
   new-conversation control, and a retry action on a failed question. All three were added,
   unit-tested (6 new tests in `tests/unit/chat.test.tsx`) and exercised in the browser.

---

## 5. Known limitations and unverified paths

These are also stated in the project README (delivered as a separate file); repeated here because a status file that omits them
would be dishonest.

- **The default embedder is lexical, not neural.** Deterministic subword hashing over word
  unigrams/bigrams and character 3–5-grams. It cannot match a paraphrase that shares no
  vocabulary; the evaluation dataset's `paraphrase` rows are the visible cost of this. The
  `sentence` provider was measured live on 2026-10-15: it **tied** the baseline on every quality
  metric of the frozen dataset — the dataset is too small and too lexical to separate the two —
  at ~8x answer latency, ~475 MB extra working memory, a ~2 GB dependency chain and a ~52 s cold
  model load. The baseline therefore stays the default on measured cost, not on measured quality
  superiority ([docs/evidence/eval-neural-vs-hashing.md](docs/evidence/eval-neural-vs-hashing.md)).
- **`ANSWER_PROVIDER=openai_compatible` was never run live** (no key available). Its failure
  paths are covered by tests with injected errors; its real output is unverified.
- **No OCR.** Scanned PDFs without a text layer are rejected rather than silently mis-read.
- **Single-process, single-user.** No authentication, no sharding, vectors held in memory with a
  lock. Do not expose it to an untrusted network.
- **The evaluation corpus is synthetic and small (18 questions, 3 documents).** Recall@5 = 1.0000
  is a statement about that corpus. No comparison against any commercial system was performed,
  and none should be inferred.
- **CI has not run on GitHub.** The workflow is written and mirrors the local commands; it has
  only been executed as those commands locally.
- **No screenshots of the UI exist.** Image capture failed in the environment used
  (non-composited webview); the browser evidence is the accessibility tree, DOM reads and the
  network log, as described in [docs/evidence/browser-walkthrough.md](docs/evidence/browser-walkthrough.md).
- **Accessibility was checked structurally** (labels, roles, focus movement, live regions,
  reduced-motion path) and not with a screen-reader session.

---

## 6. How to reproduce everything from a clean checkout

```powershell
Copy-Item .env.example .env
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                                    # 197 passed
cd ..\frontend; npm install; npm test; npm run build # 72 passed, built
cd ..; python scripts\make_sample_documents.py
# terminal 1: cd backend; uvicorn app.main:app --port 8000
python scripts\e2e_check.py                          # 59/59
python scripts\measure_evidence_gate.py              # 9/9 and 5/5
```

Nothing was pushed to GitHub. There is no git repository in this folder yet — the workflow file is
in place for when there is one.

---

## 7. 2026-10-15 later — publication cleanup and the Midnight AI theme

**Artifacts removed** (each verified to be unreferenced first):

- `.freebuff/` — Freebuff workspace metadata (a single `project-id` file), tool-local only.
- `legacy-documentation/` — a "preservation" note describing two image assets that do not exist
  anywhere in the repository, attributed to a narrative no other file mentions. Kept, it would
  misrepresent the development process; the project's real origin story is
  [docs/REFERENCE_AUDIT.md](docs/REFERENCE_AUDIT.md).
- `logs/`, `backend/install.log` — transient execution logs (CI creates its own `logs/` at runtime).
- `tools/` — a machine-local Node.js zip and extracted runtime (~100 MB), replaced by the README's
  Node 20+ prerequisite.
- `backend/.e2e-data/`, `backend/.pytest_cache/`, `frontend/test-results/`,
  `frontend/playwright-report/`, `frontend/dist/` — caches and regenerable build/test output.
- `.gitignore` extended with `.freebuff/` and `backend/.e2e-data/`.
- The root `README.md` was removed at the requester's direction; its complete text is delivered
  separately, and references to it in this file, TESTING.md and REFERENCE_AUDIT.md were rewritten
  so no documentation link breaks. `scripts/verify-readme-links.mjs` still checks it after it is
  saved back.

A repository-wide search for `freebuff`/`codebuff` over source, tests, docs, CI and config returns
**zero matches**. (The word "Freebuff" rendered by the preview panel is injected by the hosting
client outside the app's `#root`; it is not part of this codebase.)

**Midnight AI theme** — the entire palette moved to the requested design system through the token
block in `frontend/src/styles/global.css` (no scattered hard-coded values remain): Midnight Navy
`#111827` shell, Electric Violet `#8B5CF6` for primary actions and selected navigation, Cool Blue
`#60A5FA` for citations, focus rings and progress; Soft White `#F8FAFC` on Cool Gray `#9CA3AF`
text; dark borders `#374151` / light `#E5E7EB`; status `#16A34A` / `#D97706` / `#DC2626` with
light-on-dark text variants for contrast. The source viewer became a light reading surface
(`#FFFFFF` panel, `#111827` text) — the one place document text is read at length. Shadows and
radius were toned down, the old cyan/rose/amber literals and the blue `#3B82F6` were retired, and
Nova's gradient was retuned to the new blue. Only `frontend/src/styles/global.css` and
`frontend/src/components/Nova.tsx` changed (plus this ledger).

**Publication sanitisation** — the local username in evidence and audit files was replaced with
`<user>`; no measured result, command or assertion was altered.

**Verification re-run on the final tree** — backend `197 passed`; frontend `72 passed`, typecheck
and lint clean, build ok; `e2e_check.py` `59/59`; evidence gate `9/9` answered, `5/5` refused;
Playwright `7 passed`. Theme, keyboard focus (Cool Blue ring), the 420 px responsive layout (no
horizontal overflow), the six screens and the light source-viewer dialog were verified live in the
browser through computed styles and the accessibility tree — image capture still does not composite
in this environment, as noted above.
