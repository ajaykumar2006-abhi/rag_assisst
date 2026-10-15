# Security and privacy

## 1. Scope and threat model

This is a **local, single-user** application. The realistic threats are:

1. **Hostile files** — a malicious PDF/DOCX/TXT crafted to crash the extractor, exhaust
   memory, or write outside the data directory.
2. **Hostile document *content*** — text inside a document that tries to act as an
   instruction to the answering layer (prompt injection).
3. **Accidental data exposure** — secrets committed to the repository, or documents sent to
   a third party without the operator realising.
4. **Network exposure** — the API being reachable by someone else because it was bound to
   `0.0.0.0` or published behind a proxy.

Explicitly **out of scope**, and therefore called out as limitations rather than solved:
multi-tenant isolation, authentication/authorisation of API callers, and defence against an
attacker who already has code execution on the host.

## 2. Controls that are implemented

### File handling

- **Extension allow-list** — `ALLOWED_EXTENSIONS`, normalised case-insensitively.
- **Content sniffing** — `sniff_format` inspects the leading bytes; a text file renamed to
  `.pdf` is rejected with `unsupported_file` instead of being fed to the PDF parser.
- **Filename sanitisation** — path separators, drive prefixes, traversal segments
  (`../`, `..\`, `....//`), control characters and reserved Windows device names are
  stripped; the stored name is generated from a hash plus a sanitised stem. Files are always
  written inside `DATA_DIR/uploads`, and the resolved path is verified to stay there.
- **Size ceiling** — the upload body is streamed with a hard in-memory cap
  (`MAX_UPLOAD_MB`), so an oversized upload is aborted mid-stream; a second check runs on the
  final byte count.
- **Page and character ceilings** — `MAX_PAGES` and `MAX_EXTRACTED_CHARS` bound the work a
  single document can cause; exceeding them fails that document with an explicit message
  rather than hanging the process.
- **No archive expansion** — the application does not unpack archives, so zip-bomb style
  attacks are not reachable through the upload path.

### Document content is data, never instruction

The extractive answerer copies sentences; it never interprets document text as a command.
There is no code path that executes, evaluates or follows text found in a document. The test
suite asserts this directly (`test_security.py::test_instructions_inside_a_document_are_treated_as_data`)
by ingesting a document containing "IGNORE ALL PREVIOUS INSTRUCTIONS …", then checking that
the legitimate fact in the same file is answered normally, that every sentence returned is
verbatim source text, and that an unrelated question about the same document is still
refused.

For the optional generative provider, retrieved passages are passed as *quoted evidence* in a
system instruction that tells the model to answer only from them and to cite their marker.
That is mitigation, not a guarantee: a generated answer is labelled `generative` in the API
and in the UI so it is never mistaken for a quotation.

### Secrets

- Secrets are read from the environment only (`LLM_API_KEY`), via `pydantic-settings`.
- `.env` and `.env.*` are git-ignored; only `.env.example` (no values) is tracked.
- The API never returns a secret. `/settings` exposes a single boolean
  (`llm_configured`, true only when `LLM_API_KEY` is set) plus the base URL and model name,
  which are not sensitive. `answerer_available` reports whether the configured answerer can
  run; the default extractive answerer needs no key, so the UI never implies that one is
  stored.
- No credential, token or key is written into the SQLite database, the vector index, the
  frontend bundle or the logs.

### Error handling

Every error is converted to a stable envelope (`code`, `message`, `details`) with a
meaningful status. Internal failures log the traceback server-side and return a generic
message to the client, so a stack trace or absolute path is not leaked to the browser. The
exception is `processing_error`, which forwards the extractor's own message — it describes
the user's own file and is the only way to make a failure actionable.

### Data locality

`/privacy` reports measured counts and byte sizes for every artefact the application writes,
plus `external_services`, which states plainly whether retrieved passages leave the machine.
With the default configuration nothing does.

## 3. Operator responsibilities

1. **Bind to loopback.** Use `--host 127.0.0.1`. The application has no authentication; a
   publicly reachable instance lets anyone read, query and delete every document.
2. **Keep CORS tight.** `CORS_ORIGINS` should list only the origins you actually use. Do not
   add `*` while the API accepts credentials or destructive calls.
3. **Protect `.env`.** It contains your LLM API key if you enable the generative provider.
   Prefer an OS-level secret store or scoped environment variables over a file in the repo.
4. **Decide about the generative provider deliberately.** Enabling it sends the retrieved
   passages — i.e. excerpts of your documents — to that provider. The Settings screen states
   this; `/privacy` repeats it.
5. **Treat `DATA_DIR` as sensitive.** Uploads, extracted text and chat history are stored
   there unencrypted. Use full-disk encryption and a directory ACL if the machine is shared.
6. **Delete what you no longer need.** Individual documents from the Documents screen, or
   everything from Settings → Danger zone (`DELETE /privacy/documents`). Deleting the
   `DATA_DIR` after stopping the backend removes every trace.

## 4. Dependency posture

- Backend runtime dependencies are deliberately few: FastAPI, uvicorn, pydantic(-settings),
  NumPy, pypdf, python-docx, httpx. `sentence-transformers` is optional and not
  installed by default.
- The frontend has three runtime dependencies (React, React DOM, React Router) and no UI kit
  or icon package; every icon is inline SVG.
- `pip install -r requirements.txt` and `npm ci` are the supported paths; CI installs from
  the lockfiles.
