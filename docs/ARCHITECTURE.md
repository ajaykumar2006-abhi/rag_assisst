# Architecture

## 1. Shape of the system

```
Browser (React 18 + TypeScript, Vite)
   │  fetch  /api/v1/*        (dev: Vite proxies to :8000)
   ▼
FastAPI application  (backend/app/main.py)
   │
   ├─ api/            HTTP layer: parsing, validation, status codes, error envelope
   ├─ services/       pipeline · extraction · chunking · embeddings · retrieval
   │                  answering · qa · evaluation · container (composition root)
   └─ storage/        SQLite (metadata, chunks, stages, conversations, runs, events)
                      NumPy vector index on disk (vectors + manifest)
```

There is no message broker, no cache server and no external database. The single
composition root is `ServiceContainer`, created once in the app lifespan and reachable in
requests through `app.state.container`. Tests replace it with a container pointed at a
temporary data directory, which is why nothing in the application reads configuration from
module-level globals.

## 2. Request lifecycle

1. FastAPI route parses and validates the request with a Pydantic schema from
   `app/schemas/models.py` (the single source of truth for the wire contract).
2. `get_container` injects the container; the service is called.
3. Services raise typed errors (`ValidationError`, `NotFoundError`, `FileTooLargeError`,
   `UnsupportedTypeError`, `ProviderConfigError`); a global handler in `main.py` converts
   them into `{"error": {"code", "message", "details"}}` with the right HTTP status, so the
   frontend never has to parse a stack trace or guess.
4. Every mutation is written to an `events` table row (upload, answer, deletion,
   evaluation run, processing failure) which also feeds the latency statistics on the
   Evaluation screen.

## 3. Document pipeline

`services/pipeline.py` orchestrates seven stages against the database, writing progress
after each one so the Processing screen polls real state (`GET /documents/{id}/status`).

| Stage | What happens | Failure looks like |
| --- | --- | --- |
| `validate` | extension allow-list, size ceiling, `sniff_format` content check, filename sanitisation | 415 / 413 at upload time, or a failed stage |
| `extract` | pypdf per page, encoding-detected text, python-docx paragraphs + tables; page and character ceilings enforced | stage fails with the extractor's own message |
| `structure` | whitespace/hyphen normalisation, paragraph recovery, heading detection | degraded text, recorded in the stage detail |
| `chunk` | sentence-aware windows carrying page, char offsets, ordinal | chunk count 0 → later stages skip |
| `embed` | configured embedder over the chunk batch | provider fallback is logged and reported |
| `index` | vectors appended to the persistent index, chunks written to SQLite, BM25 rebuilt | index write failure |
| `verify` | re-reads the index to confirm the new chunk ids are retrievable | document marked `failed` rather than `ready` |

Indexing runs on a daemon thread started by the upload route, so a large PDF cannot block
the event loop. Progress is therefore *polled*, never assumed.

## 4. Retrieval and answering

`services/retrieval.py` runs two scorers over the same candidate chunks and fuses them:

- **dense** — cosine similarity from `storage/vector_store.py` (exact search over a NumPy
  matrix, optionally restricted to a document subset);
- **lexical** — Okapi BM25 over chunk tokens, with `df`/`avgdl` recomputed whenever the
  corpus changes.

Fusion is `(dense·w_dense + lexical·w_lexical) / (w_dense + w_lexical)`, with BM25 mapped
through a saturating curve (`score / (score + 6)`) so "sort of matches" cannot look like
"strongly matches". Both component scores travel with every result and are shown in the
citation card, so a reader can see *why* a passage surfaced.

`services/qa.py` adds the two guarantees the UI depends on:

- **evidence gate** — a fused-score floor plus a structural support rule (a passage must
  have either real keyword overlap or dense similarity above the noise band). Refusals
  return zero citations and a message naming the score that was actually achieved.
- **citation integrity** — citation `index` equals the marker used in the answer text;
  each excerpt is built around the sentences the answer actually quoted, and the window is
  guaranteed to contain them in full.

`services/answering.py` holds the providers. The default `ExtractiveAnswerer` copies
sentences verbatim, filtering out sentences that barely overlap the question and
de-duplicating repeats. The optional `OpenAICompatibleAnswerer` receives only the retrieved
passages, is instructed to cite them, and its output is labelled `generative` so fluent
prose is never presented as a document quotation.

## 5. Storage

### SQLite (`storage/db.py`)

| Table | Purpose |
| --- | --- |
| `documents` | one row per upload: filename, stored path, sha256, extension, size, status, page/char/chunk counts, embedder identity, `indexed` flag, error |
| `chunks` | chunk text with document id, ordinal, page, char offsets — the citation source of truth |
| `document_stages` | per-document stage state, detail text, timings, progress |
| `conversations`, `messages` | chat history with the citations that were returned |
| `eval_runs` | evaluation runs with their metrics and per-question cases |
| `events` | append-only log used for statistics (answers, failures, deletions) |

### Vector index (`storage/vector_store.py`)

A `float32` matrix plus chunk-id list persisted to disk with a JSON manifest recording the
embedder name and dimension. On startup the manifest is compared with the configured
embedder: a mismatch invalidates the index rather than mixing incompatible vector spaces.
Document deletion removes vectors by id prefix. Access is guarded by a re-entrant lock, and
the index exposes `size` so `/health` and `/privacy` can report real counts.

## 6. Frontend

| Layer | Files | Notes |
| --- | --- | --- |
| Transport | `services/client.ts`, `services/api.ts` | one typed function per endpoint; every failure normalised into `ApiError` with code, status and `retryable` |
| Contract | `types/api.ts` | hand-maintained mirror of the Pydantic schemas |
| State | `hooks/useAsync`, `usePolling`, `useMutation` | cancellation on unmount, backoff on failure, no double-submits |
| Shell | `context/AppContext.tsx`, `components/Layout.tsx` | health polling, toasts, motion preference, navigation |
| Screens | `pages/*` | one file per screen, each composed of the shared primitives |
| Design system | `styles/global.css` | tokens, components, animations, reduced-motion and print rules |

Rendering rules that matter: all numbers come from the API (nothing is simulated),
refusals render as refusals, errors render the backend's own message and code, and every
async surface has loading, empty and error states.

## 7. Concurrency and resource use

- One worker thread per document; the container's indexes are lock-protected, so
  concurrent uploads serialise on write and stay correct.
- Ingestion is streaming with a hard in-memory ceiling (`MAX_UPLOAD_MB`), so an oversized
  upload is rejected mid-stream instead of exhausting memory.
- Retrieval is exact search over a NumPy matrix: O(chunks) per query, microseconds for
  laptop-scale corpora, and intentionally not an approximate index.
- The vector index and BM25 statistics are rebuilt from SQLite on startup, so a crash
  cannot leave them inconsistent with the metadata.

## 8. Extension points

- **Embedder** — implement `Embedder` in `services/embeddings.py` and register it in
  `build_embedder`; the manifest will invalidate existing vectors.
- **Answer provider** — implement `Answerer` in `services/answering.py`; return
  `AnswerDraft` and set `used_sentences` if you copy text verbatim.
- **Evaluation dataset** — drop a JSON file in `eval/datasets/` following the shape of
  `synthetic_galaxy.json`; it appears in `/evaluation/datasets` automatically.
