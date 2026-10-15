# Browser walkthrough — the six screens, driven by hand

**When:** 2026-10-13, session after the final code changes.
**What was running:** `uvicorn app.main:app` on `http://127.0.0.1:8000` with `DATA_DIR=backend/data-verify`
(a cold, empty directory) and `npm run dev` (Vite 6.0.5) on `http://127.0.0.1:5173`.

This is a record of what was actually observed in a real browser session, screen by screen.
Screenshots could not be captured in this environment — the embedded preview webview never
became composited, so image capture failed for every attempt. Verification below therefore
comes from the page's accessibility tree and from reading live DOM text and internal state,
which is weaker than a screenshot but is not an assumption: every quoted value was read out of
the running page.

---

## 1. Welcome (`/`)

- Sidebar reported **Backend online**, `Embeddings: hashing-subword-v1`, `Answers: extractive`.
- After a PDF was ingested, the "Live system state" card read **1 document indexed / 5 indexed
  chunks / 1 of 1 ready / 4.0 KB stored locally** — matching
  `GET /api/v1/documents` and `GET /api/v1/health` for the same instant.
- Nova's line updated accordingly ("… I have 1 document indexed.").
- The stage list under "What happens to a document" described extraction with **pypdf**. This
  walkthrough caught the opposite claim in the UI copy — it said `pdfplumber`, a library this
  project does not use — and the copy was corrected.

## 2. Documents (`/documents`)

- Table showed `helios_mission_brief.pdf`, status `Ready`, **2 pages**, **5 chunks**, `4.0 KB`,
  `12m ago`, with per-row `Pipeline`, `Ask` and `Delete` actions and a multi-select checkbox.
- Counters read `DOCUMENTS 1 / READY 1 / IN PROGRESS 0 / FAILED 0`.

## 3. Processing (`/processing`, `/processing/:id`)

- Detail view for the document listed all seven stages as `completed` with the backend's own
  timings and details: `validate 23 ms · 4,087 bytes, format=PDF`, `extract 23 ms · 3,083
  characters from 2 unit(s)`, `structure 2 ms`, `chunk 1 ms · 5 chunks (~900 chars, 150
  overlap)`, `embed 70 ms · 5 × 512d vectors`, `index 14 ms · index now holds 5 vectors on
  disk`, `verify 2 ms · 5 chunks retrievable`.
- The five chunks were listed with their real page and character ranges
  (`page 1 · chars 0–893`, `page 2 · chars 2837–3085`, …).
- **Two display bugs were found here and fixed:**
  - The progress header asserted `Queued 0%` before any status response had arrived. It now
    says `Waiting for status… / No status response yet` until the first response, so an
    unfetched status is never presented as a real one.
  - The bucket view showed the "nothing to process yet" empty state while the document list
    had simply not loaded. `usePolling` skips *subsequent* ticks while a tab is hidden; it now
    always runs its first request, so a page opened in a background tab renders its real
    records. This was reproduced in the browser, fixed, and re-observed (the document then
    listed correctly); a unit test now pins the behaviour.
- After both fixes the detail view read `Ready · Indexed · 100% complete` with the "Indexing
  finished…" note, verified again after a reload.

## 4. Ask (`/chat?docs=…`)

- The question box accepted input immediately, with the document pre-selected
  (`Searching 1 document.`).
- Asked *"What altitude and inclination does the observatory orbit at?"* → the answer was
  assembled from the document: *"The observatory operates in a low Earth orbit at an altitude
  of 612 kilometres with an inclination of 28.5 degrees [1]."* — flagged
  `Extractive — verbatim from your documents`, `answered in 6 ms`.
- The answer carried a real citation control with `aria-label="Show source 1:
  helios_mission_brief.pdf"`, and its source card showed `page 1`, chunk id
  `doc_b21f914927c543fa::00000`, and the score breakdown
  (blended 0.3521 · vector 0.3063 · lexical 0.4370).
- Clicking the citation opened the **Source viewer** dialog: *"Source [1] ·
  helios_mission_brief.pdf — Page 1 · characters 0–893 of the extracted text"*, the verbatim
  passage, and the score explanation. Focus moved to the dialog's `Close source context`
  button, and Escape closed it.
- The conversation persisted (`2 messages in this session`, `CITATIONS 1`).

## 5. Evaluation (`/evaluation`)

- Live statistics were read from the running instance, not hard-coded: `DOCUMENTS 1`,
  `CHUNKS INDEXED 5`, `QUESTIONS ANSWERED 22`, `MEAN ANSWER LATENCY 5 ms (p95 6 ms)`.
- Pressing **Run evaluation now** executed the dataset in the browser and rendered
  Recall@5 `1.0000`, Precision@5 `24.4%`, MRR `1.0000`, citation hit rate `100.0%`,
  answer rate `100.0%`, mean latency `2 ms`, plus all 18 per-question rows, the methodology
  text and the known-limitations list. The run wrote
  `eval/results/eval_20261013T141138.json`.
- The previously recorded run (`eval_20261013T140233`, recall `1.0000`, MRR `1.0000`) was
  listed in the persisted-runs table.

## 6. Settings & privacy (`/settings`)

- Retrieval and chunking controls, provider identities, upload limits, accepted extensions and
  CORS origins were all present.
- "What is stored on this machine" measured the filesystem on screen:
  `uploads 1 file / 4.0 KB`, `metadata.sqlite3 5 rows / 4.0 KB`,
  `indexes/collection 5 vectors / 10 KB`, with the delete instructions and danger zone.
- This screen exposed the third wording bug fixed in this session: it claimed
  **"API key configured: yes"** while no key exists anywhere, because the API field behind it
  meant "the configured answerer can run" — which is true for the local extractive answerer
  that needs no key. The API now separates `llm_configured` (a key is stored) from
  `answerer_available` (the answerer can run), and the screen reads
  **"Generation API key: not set — Not needed: answers are extractive and local"** alongside
  **"Answer provider ready: yes"**.

## 7. Deletion through the UI

- `Delete` on the row opened a confirm dialog: *"helios_mission_brief.pdf will be removed from
  the document store, its chunks deleted from the vector index, and its stored file removed
  from disk. This cannot be undone…"* with `Cancel` / `Delete permanently`.
- After confirming, `GET /api/v1/documents` returned `[]` and the page showed its empty state.

## 8. Ask screen additions — exercised 2026-10-15

Driven in a real Chromium tab against the dev server (:5173) with the backend on :8000,
after the Ask-screen and conversation-context work landed:

- **Copy answer.** Asked a known-answer question against a selected document, clicked the
  copy button on the rendered answer; the clipboard received the answer text (verified
  through the page, not assumed from the handler's existence).
- **New conversation.** With a stored thread containing exchanges, clicked the
  new-conversation control: the transcript cleared to its welcome state and the previous
  thread remained listed and loadable — history was not deleted.
- **Failed question + retry.** Covered by jsdom unit tests
  (`frontend/tests/unit/chat.test.tsx`): a failed question renders exactly one inline error
  with a working retry action, and the page-level banner does not duplicate it.
- **Conversation-context gate (backend, live API probe).** Inside a real conversation, an
  out-of-scope follow-up returned `insufficient` with zero citations, and a vague
  in-conversation follow-up resolved through widened retrieval — confirmed by three backend
  tests in `test_api_qa.py` as well.

## Console and network

Collected across the session: no `error` or `warning` entries from application code. The only
warnings are React Router v6's own future-flag notices (`v7_startTransition`,
`v7_relativeSplatPath`). Every request logged (`/health`, `/documents`, `/settings`,
`/privacy`, `/evaluation/*`, `/qa/*`) returned 200 except the deliberately-missing 404 checks.

## What this does not cover

- No screen-reader or screen-magnifier session was run; accessibility was checked only through
  labels, roles and focus behaviour visible in the accessibility tree.
- No screenshots, as explained above.
- The optional `ANSWER_PROVIDER=openai_compatible` was not exercised anywhere (no API key
  available). The optional `EMBEDDING_PROVIDER=sentence` was exercised live on 2026-10-15
  through the API and the evaluation pipeline (not through the browser UI); its measured
  comparison is in [eval-neural-vs-hashing.md](eval-neural-vs-hashing.md).
