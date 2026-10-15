# RAG Document Intelligence — Galaxy Edition

Ask questions about your own PDF, TXT and DOCX files and get answers you can check. Every
sentence of every extractive answer is copied verbatim out of a retrieved passage, and every one
carries a citation back to the exact document, page and character range it came from.

The whole pipeline — extraction, chunking, embeddings, vector indexing, semantic retrieval and
grounded answering — runs locally. The default configuration needs no API key and is comfortable
on a CPU-only laptop.

- **Frontend:** React 18 + TypeScript + Vite, hand-written CSS design system in the Midnight AI
  palette, no UI kit.
- **Backend:** FastAPI + SQLite + NumPy vector index, no external services required.
- **Screens:** Welcome (a live galaxy and Nova the assistant), Documents, Processing,
  Ask, Evaluation, and Settings & privacy.
- **Verification:** backend tests, frontend tests, a synthetic evaluation dataset, a live
  end-to-end harness, an evidence-gate measurement, and a Playwright browser suite — all
  executed from the same repository and summarised below.

<details>
<summary>A quick look</summary>

The welcome screen opens on a small animated galaxy and an in-character assistant, Nova.
Nova is personality, not a separate service: she introduces the product in her own voice, reports
the actual state of the running backend, and gives you a clean path into the rest of the app.

</details>

---

## 1. The experience in one sentence

Drop a document into the workspace, watch it move through seven real stages on the Processing
screen, select it on Ask, and ask a question whose answer you already know. The answer comes back
with a `[1]` marker; click it and you see the exact quoted passage, the page it came from, and the
score breakdown that made retrieval choose it. Ask a question the documents cannot support, and Nova
says so instead of guessing.

## 2. What each screen does well

**Welcome (`Your documents at a glance`)**

A live galaxy with Nova, the app's assistant. The side rail reads the backend directly — embedding
provider, answer mode, number of indexed documents, uptime, stored bytes. The animation toggle
respects `prefers-reduced-motion` and persists your choice. The pipeline explainer underneath
shows the seven stages with plain-language descriptions, so you can see what happens before you
upload anything.

**Documents (`Your library`)**

A file dropzone with clear accept rules, per-file status, and a library table with progress,
ready/failed counts and per-document actions. Select two or more rows to question several documents
at once.

**Processing (`The observatory`)**

Seven stages: `validate → extract → structure → chunk → embed → index → verify`. Each stage is a
real backend row with timings and detail text, not a decorative loading bar. Tabs expand the image,
content, chunk list and stored sources; a retry control re-runs from validation when a document
fails.

**Ask (`Ground-truth questions`)**

Type a question, or choose one of the built-in starter prompts. Answers are extractive by default:
copied verbatim, one citation per sentence, with a sources modal that shows the blended score, vector
similarity, keyword overlap, page, chunk id and the full quoted passage. A settings button on Ask
lets you tune top-k per question without changing the saved defaults.

Follow-up questions keep the thread's context: when a follow-up's own words are too vague to pass
the evidence gate ("what about the second one?"), retrieval is retried once with your earlier
questions in the thread added to the query — but the same gate judges the result and the answerer
still scores passages against the current question alone, so an out-of-scope follow-up is still
refused. Every answer has a copy button, a failed question offers a retry, and a new-conversation
button starts a fresh thread without deleting the stored history.

**Evaluation (`Measured, not estimated`)**

The dashboard reads this instance's SQLite event log and index for live stats — documents,
chunks, questions answered, mean latency — then runs the synthetic dataset through the same pipeline
the chat screen uses and renders recall, precision, MRR, citation hit rate, answer rate and per-question
results with the full methodology and known-limitations text. Your own documents are never touched.

**Settings & privacy (`What stays on this machine`)**

Retrieval and chunking knobs, provider identities, upload limits, accepted extensions, CORS origins.
Retrieval changes apply immediately. Provider changes need a restart and are flagged as such. The
storage section measures the filesystem on request — uploads, SQLite, vector index — with retention
info, external-service status and clear delete instructions, plus a danger zone for removing
everything.

## 3. What makes this project different

**Answers you can verify.** Extractive answers are assembled only from retrieved passages, and each
sentence carries a citation. Refusals are explicit, with no citations, and the evidence-gate script
measured that the system answers the questions it should and refuses the ones it shouldn't.

**Every number is measured.** The evaluation dashboard calls the real retriever and answerer through
the same code path the UI uses. The README's metrics, the testing doc and the build-progress file all
come from the same executed commands and their stored evidence.

**The app is private by architecture, not by promise.** Everything the app writes lives in its own
data directory. There is no cloud service here; an API key is optional and only for the provider the
app does not use by default. The settings endpoint never returns a key.

**The look is one design system, not scattered colors.** Every color comes from a single token block
in `frontend/src/styles/global.css` — the Midnight AI palette: Midnight Navy `#111827` shell,
Electric Violet `#8B5CF6` for primary actions and selected navigation, Cool Blue `#60A5FA` for
citations, focus rings and progress, Soft White `#F8FAFC` on Cool Gray `#9CA3AF` text, and the
status colors `#16A34A` / `#D97706` / `#DC2626`. The source viewer is a light reading surface
(`#FFFFFF` on `#111827` text) because that is where document text is read at length. The galaxy,
Nova, and the reduced-motion path are part of that same system: one switch stops all motion without
breaking keyboard access, labels or live regions.

## 4. What it cannot do yet — written plainly

- The default embedder is lexical, not neural. It matches surface form and morphology. It does not
  match a paraphrase that shares no vocabulary. The optional sentence-transformers provider was
  installed and measured live on 2026-10-15 against the same frozen dataset: it **tied** the lexical
  baseline on every quality metric (both are perfect on this small dataset, so it cannot separate
  them) at ~8x the answer latency and ~475 MB more memory. It stays optional and the lexical
  provider stays the default; see
  [docs/evidence/eval-neural-vs-hashing.md](docs/evidence/eval-neural-vs-hashing.md).
- Scanned or photographed PDFs without a text layer are not supported. There is no OCR.
- PDF page numbers only exist when the extractor can attribute text to a page. DOCX and TXT citations
  use character offsets instead, and the UI states that on screen.
- Indexing is single-process, in-memory with a lock, and durable to disk — fine for a laptop, wrong
  for a fleet. There is no sharding and no authentication. Do not publish this to an untrusted network.
- The evaluation dataset is synthetic and small. The reported recall is a statement about that dataset
  and that configuration, not a general accuracy claim, and no comparison with any commercial system was
  run.

## 5. Verified on a real machine

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `python -m pytest` in `backend/` | **197 passed** |
| Frontend unit tests | `npm test` in `frontend/` | **72 passed** across 7 files |
| Frontend typecheck | `npm run typecheck` | **clean** |
| Frontend lint | `npm run lint` (`eslint --max-warnings 0`) | **clean** |
| Production build | `npm run build` | **263.2 kB JS** (81.9 kB gzip), 19.4 kB CSS |
| Live end-to-end | `python scripts/e2e_check.py` | **59/59 checks passed** |
| Evidence gate | `python scripts/measure_evidence_gate.py` | **9/9 in-scope answered, 5/5 refused** |
| Retrieval evaluation | `POST /api/v1/evaluation/run` | recall@5 **1.000**, MRR **1.000**, citation hit **1.000** |
| Neural embedding evaluation | same run with `EMBEDDING_PROVIDER=sentence` | tied quality, 19.1 ms vs 2.4 ms latency ([comparison](docs/evidence/eval-neural-vs-hashing.md)) |
| Browser end-to-end | `npm run test:e2e` (Chromium) | **7 passed** |

All of the above were re-run on the final tree on 2026-10-15. The live run used a cold data
directory, so the pipeline was exercised from an empty index and the stored files, chunks and
vectors were re-read after a server restart. Full numbers and raw logs live in
[`docs/evidence/`](docs/evidence).

---

## 6. Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.11+ | 3.13.5 was used here. |
| Node.js 20+ | 22.23.3 was used here. Only needed for the frontend. |
| No GPU, no API key | Optional extras are opt-in and documented in `.env.example`. |

---

## 7. First time setup (Windows PowerShell)

```powershell
# From the project root.
cd rag-document-intelligence

# 1. Configuration
Copy-Item .env.example .env

# 2. Backend: virtual environment and dependencies
cd backend
python -m venv .venv
.\\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt            # runtime
python -m pip install -r requirements-dev.txt        # tests + fixtures
cd ..

# 3. Frontend dependencies
cd frontend
npm install
cd ..
```

### Bash / macOS / Linux

```bash
cp .env.example .env
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt -r requirements-dev.txt
cd ../frontend && npm install
```

---

## 8. Run it

Two terminals, or one command each.

```powershell
# Terminal 1 — backend on http://127.0.0.1:8000
cd backend
.\\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2 — frontend on http://127.0.0.1:5173
cd frontend
npm run dev
```

Then open <http://127.0.0.1:5173>. The Vite dev server proxies `/api` to the backend, so no CORS
configuration is needed during development.

### Try it with real files

```powershell
python scripts\make_sample_documents.py      # creates real PDF/TXT/DOCX fixtures
python scripts\e2e_check.py                  # drives the whole flow against a running server
python scripts\measure_evidence_gate.py      # measures refusal quality
```

In the browser: **Documents → upload `eval/fixtures/helios_mission_brief.pdf` → watch Processing →
Ask "What altitude and inclination does the observatory orbit at?"** The answer is quoted from the
document with a `[1]` marker that opens the cited passage, page number included.

---

## 9. Tests, checks and CI

```powershell
# Backend: 197 tests cover extraction, chunking, embeddings, index persistence, retrieval fusion,
# answering, the evidence gate, conversation context, the API contract and security.
cd backend; .\\.venv\Scripts\python.exe -m pytest

# Frontend: 72 unit tests across formatting/parsing, HTTP client error handling, polling/async hooks,
# components, the Ask-screen question flow, and Welcome-screen integration — all against a typed
# contract, not mocked responses.
cd frontend; npm test

# Static checks and production build.
npm run typecheck; npm run lint; npm run build

# Browser end-to-end (needs both servers running).
npx playwright install chromium    # once
npm run test:e2e
```

CI is wired in [.github/workflows/ci.yml](.github/workflows/ci.yml). It mirrors these commands
exactly: backend lint + test (Python 3.11 and 3.13), backend integration against a live server with
real documents (e2e + evidence gate), frontend typecheck + lint + test + build, and a Chromium
Playwright run that brings the real stack up itself. The workflow has **not** run on GitHub — it has
only been executed as these same commands locally, where they pass. No file in this repository
depends on a local setup to be green; CI is deterministic, offline for the default embedder, and
requires no API key.

## 10. Project layout

```
rag-document-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/            routes_health, routes_documents, routes_qa,
│   │   │                   routes_evaluation, routes_settings, deps
│   │   ├── core/           config (env-driven settings), errors, logging
│   │   ├── schemas/        Pydantic request/response models (the API contract)
│   │   ├── services/       extraction, chunking, embeddings, retrieval,
│   │   │                   answering, qa, evaluation, pipeline, container
│   │   ├── storage/        SQLite metadata + persistent NumPy vector index
│   │   └── main.py         app factory, CORS, error handlers, lifespan
│   ├── tests/              197 pytest tests + fixtures
│   └── data/               created at runtime (uploads, metadata.sqlite3, indexes/)
├── frontend/
│   ├── src/
│   │   ├── components/     Nova, GalaxyBackground, Layout, DocumentDropzone,
│   │   │                   DocumentTable, CitationCard, SourceViewer,
│   │   │                   ChatTranscript, ErrorBoundary, ui/* primitives
│   │   ├── pages/          Welcome, Documents, Processing, Chat, Evaluation, Settings
│   │   ├── services/       client (HTTP + typed errors), api, format, scope
│   │   ├── hooks/          useAsync, usePolling, useMutation, useReducedMotion
│   │   ├── context/        AppContext (health, toasts, motion preference)
│   │   ├── types/          api.ts — typed mirror of the backend contract
│   │   └── styles/         global.css — Midnight AI tokens, components, animations, a11y
│   └── tests/              72 unit tests + Playwright specs
├── eval/
│   ├── datasets/           synthetic_galaxy.json (18 questions, verbatim ground truth)
│   └── fixtures/           generated real PDF/TXT/DOCX samples
├── scripts/                make_sample_documents, e2e_check, measure_evidence_gate
├── docs/                   ARCHITECTURE, API_CONTRACT, TESTING, SECURITY,
│                           EVALUATION, REFERENCE_AUDIT, evidence/
└── .github/workflows
    └── ci.yml
```

## 11. How the pipeline works

Seven stages, each reported on the Processing screen:

1. **Validate** — extension allow-list, size ceiling, filename sanitisation, content sniffing so a
   plain-text file pretending to be a PDF is rejected.
2. **Extract** — `pypdf` per page with page numbers preserved, encoded text files with encoding
   detection, `python-docx` paragraphs and tables. Page and character ceilings are enforced here.
3. **Structure** — whitespace and hyphenation normalisation, blank-line paragraph recovery, heading
   detection.
4. **Chunk** — sentence-aware windows with configurable size and overlap, each carrying a page,
   character offsets and an ordinal.
5. **Embed** — the configured embedder. Default: deterministic subword hashing vectors. Optional:
   a local neural model once you install `sentence-transformers`.
6. **Index** — vectors appended to the persistent NumPy index, chunks written to SQLite, BM25
   statistics rebuilt.
7. **Verify** — the index is re-read to prove the new vectors are retrievable before the document
   is marked ready.

Retrieval fuses dense cosine similarity with BM25 keyword overlap; the weights are configurable and
the fused score has a minimum-relevance floor below which the assistant says there is insufficient
evidence. Answering is extractive by default: the most question-relevant sentences are copied verbatim,
one citation per sentence. An optional OpenAI-compatible provider can be switched on for fluent prose;
its output is labelled `generative` so it is never mistaken for a quotation.

## 12. Where the ideas came from

Three projects in the referenced `101_Python_Mini_Projects_Full_Code.pdf` were read directly before
anything was reused. The audit — what each one actually contains, and what was and was not taken from
it — is in [docs/REFERENCE_AUDIT.md](docs/REFERENCE_AUDIT.md).

In short, the file-discovery and keyword-ranking ideas from project 90 informed the upload workspace
conceptually, but everything that makes this a real RAG system — extraction, chunking, embeddings,
vector indexing, hybrid retrieval, grounded answering, evaluation — was written from scratch because
none of the referenced projects implements any of it. Project 71's pitch is PDF text search; the code
shown is SQLite CRUD, so no PDF extraction or indexing behaviour was assumed. Project 72's pitch is
OCR; the code shown is a keyword-search script over existing text, so OCR is documented as future work
rather than reimplemented.

## 13. Documentation index

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map, data flow, storage schema, concurrency model |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Every endpoint, request/response shape, error envelope, privacy endpoints |
| [docs/TESTING.md](docs/TESTING.md) | Test strategy, commands, what is not covered |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, controls, operator guidance |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Dataset, metric definitions, measured results, reading the numbers honestly |
| [docs/REFERENCE_AUDIT.md](docs/REFERENCE_AUDIT.md) | Audit of the three referenced mini-projects |
| [BUILD_PROGRESS.md](BUILD_PROGRESS.md) | Status ledger: finished, what changed, what remains, honest limitations |

## 14. Environment variables

`cp .env.example .env` is the starting point. The defaults below need no API key and no download.

```
APP_NAME, API_PREFIX, DEBUG
DATA_DIR
MAX_UPLOAD_MB, MAX_PAGES, MAX_EXTRACTED_CHARS, MAX_CHUNKS_PER_DOCUMENT, ALLOWED_EXTENSIONS
CHUNK_SIZE, CHUNK_OVERLAP
EMBEDDING_PROVIDER (hashing|sentence), EMBEDDING_MODEL, EMBEDDING_DIM
TOP_K, DENSE_WEIGHT, LEXICAL_WEIGHT, MIN_RELEVANCE
ANSWER_PROVIDER (extractive|openai_compatible), ANSWER_MAX_SENTENCES
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
CORS_ORIGINS
```

Everything the app writes is configurable under `DATA_DIR`, so you can point it at a different
directory, run several instances on different ports with different data, or reset the whole thing by
removing the directory.

## 15. Known limitations (restated)

- **Default embedder is lexical.** It matches surface form and morphology; it misses paraphrases.
- **No OCR.** Scanned PDFs with no text layer are unsupported.
- **PDF page numbers only exist when the extractor can attribute text to a page.** DOCX and TXT use
  character offsets.
- **Single-process, single-user.** No authentication, no sharding.
- **The evaluation dataset is synthetic and small.** Reported recall is about that dataset only.
- **The `sentence` embedding provider is exercised live** (`pip install sentence-transformers`,
  ~90 MB model download): it matched the lexical baseline on the synthetic dataset at ~8x latency and
  ~475 MB extra memory, so it remains optional rather than default
  ([measured comparison](docs/evidence/eval-neural-vs-hashing.md)). The **OpenAI-compatible answer
  provider was not exercised live** (no API key); its failure paths are unit-tested.
- **No UI screenshots exist** in this build because the capture tool did not render the preview page.
  The browser evidence is the accessibility tree, computed styles and the network log.
- **CI has not run on GitHub.** The workflow mirrors the local commands, which pass.

---

If you build this on another machine, the fastest way to trust it is the same order this project used:
install, run the backend tests, run the frontend checks, start both servers, run `e2e_check.py`, and
only then open the app and ask a question with a known answer. That is the sequence that proved the
pipeline behaves like itself, and the numbers above are the output of that sequence.
