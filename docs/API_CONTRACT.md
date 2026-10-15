# API contract

Base path: `/api/v1` (configurable with `API_PREFIX`). Interactive docs are served at
`/docs` (Swagger UI) and `/redoc` by FastAPI itself.

## Error envelope

Every non-2xx response uses one shape, produced by the handlers in `app/main.py`:

```json
{
  "error": {
    "code": "file_too_large",
    "message": "The file exceeds the 25 MB upload limit.",
    "details": { "limit_mb": 25 }
  }
}
```

| `code` | HTTP | Raised when |
| --- | --- | --- |
| `validation_error` | 422 | invalid parameters, inconsistent settings, unknown dataset, request body that fails schema validation |
| `unsupported_file` | 415 | extension not allowed, or the bytes do not match the extension |
| `file_too_large` | 413 | upload exceeds `MAX_UPLOAD_MB` |
| `extraction_failed` | 422 | the file is the right type but no text could be recovered from it |
| `not_found` | 404 | unknown document, conversation, chunk or evaluation run |
| `conflict` | 409 | the request contradicts current state (for example deleting a document mid-index) |
| `provider_not_configured` | 400 | a generative answer provider was selected but has no API key or model set |
| `processing_failed` | 500 | a pipeline failure surfaced directly by a request |
| `http_error` | varies | any `HTTPException` raised inside a route (404/405 for unmatched routes and methods) |
| `internal_error` | 500 | unhandled exception (message is generic; the traceback is logged, never returned) |

The frontend maps these onto `ApiError` (`services/client.ts`) and shows the message and
code verbatim; `retryable` is true for 408/429/5xx and transport failures only.

---

## Health

### `GET /health`

```json
{
  "status": "ok",
  "app_name": "RAG Document Intelligence",
  "version": "1.0.0",
  "embedding_provider": "hashing-subword-v1",
  "embedding_dim": 512,
  "answer_provider": "extractive",
  "generative_available": false,
  "documents_indexed": 3,
  "data_dir": "C:\\...\\backend\\data",
  "uptime_seconds": 128.4
}
```

---

## Documents

### `POST /documents` — multipart upload, field `file`

`201` →

```json
{ "document": { /* DocumentDetail */ }, "message": "Upload accepted. Indexing has started." }
```

The file is streamed with a hard in-memory ceiling, the extension is checked against
`ALLOWED_EXTENSIONS`, and the first bytes are sniffed so a text file renamed to `.pdf` is
rejected before anything is stored. Indexing runs on a background thread; poll the status
endpoint for progress.

### `GET /documents` → `DocumentSummary[]`

### `GET /documents/{id}` → `DocumentDetail` (includes the seven stage records)

### `GET /documents/{id}/status`

```json
{
  "id": "doc_...",
  "status": "processing",
  "stages": [{ "name": "embed", "label": "Embed chunks", "state": "running",
               "detail": "embedding 12 of 40 chunks", "progress": 0.3,
               "started_at": "...", "finished_at": null }],
  "progress": 0.62,
  "error": null,
  "retryable": false,
  "indexed": false
}
```

`retryable` is true only for `failed` documents, which is what enables the Retry button.

### `GET /documents/{id}/sources?limit=50`

The document's indexed chunks in order, as `Citation` objects with `score = 0` (they are
not ranked here). Used by the Processing screen's chunk inspector.

### `DELETE /documents/{id}`

```json
{ "deleted": "doc_...", "filename": "report.pdf",
  "vectors_removed": 12, "files_removed": 1, "index_size_after": 0 }
```

### `POST /documents/{id}/retry` → `202`

Re-resets the stage records, drops any partial chunks/vectors for that document and starts
the pipeline again from `validate`.

---

## Questions

### `POST /questions` — search a set of documents

### `POST /documents/{id}/questions` — search one document

Request body (`QuestionRequest`):

```json
{ "question": "What altitude is the orbit?", "document_ids": ["doc_..."],
  "top_k": 5, "conversation_id": "conv_..." }
```

`document_ids` omitted or `null` means "every indexed document". Unknown ids are a `404`.

Response (`AnswerResponse`):

```json
{
  "question": "What altitude is the orbit?",
  "answer": "The observatory operates in a low Earth orbit at an altitude of 612 kilometres with an inclination of 28.5 degrees [1].",
  "answer_mode": "extractive",
  "insufficient_evidence": false,
  "citations": [{
    "index": 1, "document_id": "doc_...", "filename": "brief.pdf",
    "chunk_id": "doc_...::00000", "page": 1,
    "score": 0.3521, "dense_score": 0.3063, "lexical_score": 0.437,
    "excerpt": "...", "char_start": 0, "char_end": 1284
  }],
  "retrieved_count": 3,
  "latency_ms": 2.1,
  "embedding_provider": "hashing-subword-v1",
  "conversation_id": "conv_...",
  "notice": "Extractive answer: every sentence above is copied verbatim from the cited passages."
}
```

Contract guarantees the UI relies on:

- `answer_mode` is one of `extractive`, `generative`, `insufficient`; nothing is presented
  as a quotation unless it is one.
- when `insufficient_evidence` is true, `citations` is **empty** — a refusal never carries a
  reference.
- every `[n]` marker in `answer` has a citation whose `index` is exactly `n`
  (`Citation.index` is the marker, not a re-numbered position).
- each citation's `excerpt` contains, in full, every sentence of that chunk that the answer
  quoted.
- `page` is `null` when the format has no page concept (TXT/DOCX) — the UI says so instead
  of showing a fake number.
- when a question is sent with a `conversation_id` and its own words fail the evidence gate,
  the server retries retrieval **once** with that conversation's recent user questions added
  to the query; the same gate judges the expanded result and sentences are still scored
  against the current question alone, so an out-of-scope follow-up is still refused with
  `insufficient_evidence: true` and no citations.

---

## Conversations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/conversations` | list stored conversations (id, title, counts, timestamps) |
| `POST` | `/conversations` | create one; body `{ "document_ids": [...], "title": "..." }` |
| `GET` | `/conversations/{id}` | full history with the citations each answer returned |
| `DELETE` | `/conversations/{id}` | delete one |
| `DELETE` | `/conversations` | delete all, returns `{ "conversations_removed": n }` |

Passing `conversation_id` with a question records the question, the answer, the citations
and the latency in that conversation. Prior questions from the same conversation may widen
retrieval for vague follow-ups (see the guarantees above), but never bypass the evidence
gate and never leak into other documents' conversations.

---

## Settings

### `GET /settings` → `SettingsResponse`

Includes the effective retrieval parameters, chunking parameters, provider identities,
upload limits, allowed extensions, CORS origins and two lists the UI renders verbatim:
`runs_locally` and `requires_external_service`.

Three provider fields are distinct on purpose and are never conflated:

| Field | Meaning |
| --- | --- |
| `answer_provider` | `extractive` (local, default) or `openai_compatible` |
| `answerer_available` / `answerer_reason` | Whether the configured answerer can run right now and, if not, the missing environment variables. The local extractive answerer is always available. |
| `llm_configured` | Literal: an external provider's `LLM_API_KEY` is set. It is `false` in the default configuration, where no key exists at all. |

### `PATCH /settings`

Body is a partial `SettingsUpdate`: `chunk_size`, `chunk_overlap`, `top_k`, `dense_weight`,
`lexical_weight`, `min_relevance`, `answer_max_sentences`.

```json
{ "settings": { /* SettingsResponse */ }, "applied": true,
  "notice": "Chunking changes apply to documents indexed from now on; re-upload to re-chunk." }
```

Two fields are rejected on purpose: changing `embedding_provider` or `answer_provider` at
runtime requires a restart (the vector index would otherwise mix incompatible vector
spaces, and the provider must validate its configuration at startup). Attempting it returns
`validation_error` naming the environment variable to set instead of silently doing
nothing.

---

## Privacy

### `GET /privacy`

```json
{
  "data_dir": "C:\\...\\backend\\data",
  "storage": [
    { "what": "Uploaded documents", "where": "...\\uploads", "count": 3, "bytes": 51234 },
    { "what": "Document metadata, chunks and chat history", "where": "...\\metadata.sqlite3",
      "count": 42, "bytes": 233472 },
    { "what": "Vector index", "where": "...\\indexes\\collection", "count": 42, "bytes": 86016 }
  ],
  "retention": "Documents and their indexes persist until you delete them here ...",
  "external_services": "None configured.",
  "delete_instructions": ["Delete an individual document ...", "Delete everything: ..."]
}
```

Counts and byte sizes are measured from the filesystem on request, not estimated.

### `DELETE /privacy/documents`

Deletes every document, its chunks, its vectors and its stored file:
`{ "documents_removed": 3, "index_size_after": 0 }`.

---

## Evaluation

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/evaluation/summary` | live counts and answer-latency statistics from the event log |
| `GET` | `/evaluation/datasets` | dataset file names found in `eval/datasets` |
| `GET` | `/evaluation/runs` | previously recorded runs with their metrics |
| `POST` | `/evaluation/run` | execute a dataset; body `{ "dataset", "top_k", "limit" }` |

`POST /evaluation/run` ingests the dataset's documents into an **isolated** collection, runs
every question through the production retrieval and answering code, and returns:

```json
{
  "run_id": "eval_20261013T141732",
  "dataset": "synthetic_galaxy",
  "created_at": "2026-10-13T14:17:32Z",
  "sample_count": 18,
  "top_k": 5,
  "recall_at_k": 1.0,
  "precision_at_k": 0.244444,
  "mrr": 1.0,
  "citation_hit_rate": 1.0,
  "answer_rate": 1.0,
  "mean_latency_ms": 3.452,
  "cases": [ /* per question: retrieved ids, relevant ids, recall, precision, RR, citation_hit, mode, latency */ ],
  "methodology": "Each dataset document is ingested through the production pipeline ...",
  "limitations": [ "The dataset is synthetic and small; ...", "..." ],
  "result_path": "C:\\...\\eval\\results\\eval_20261013T141732.json"
}
```

`methodology` and `limitations` are part of the response so any client that displays a metric
also has the caveat available; the Evaluation screen renders both.

---

## Types

`DocumentSummary`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | `doc_<hex>` |
| `filename` | string | sanitised original name |
| `extension` | string | with leading dot |
| `size_bytes` | int | original upload size |
| `status` | `queued \| processing \| ready \| failed` | |
| `created_at`, `updated_at` | ISO-8601 string | |
| `page_count` | int \| null | PDFs only |
| `chunk_count`, `char_count` | int | |
| `error` | string \| null | the extractor's own message on failure |

`Stage`

| Field | Type |
| --- | --- |
| `name` | `validate \| extract \| structure \| chunk \| embed \| index \| verify` |
| `label`, `detail` | string |
| `state` | `pending \| running \| completed \| failed` |
| `progress` | 0..1 |
| `started_at`, `finished_at` | ISO-8601 \| null |

The TypeScript mirror of every type lives in `frontend/src/types/api.ts`; the frontend
compiles against it, so a drift in this document shows up as a type error rather than a
runtime surprise.
