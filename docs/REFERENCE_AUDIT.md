# Reference audit

The task brief pointed at three projects in
`101_Python_Mini_Projects_Full_Code.pdf` and asked, explicitly, that I check what their code
*actually does* before reusing anything. This document records that check, with the evidence.

- **Source:** `101_Python_Mini_Projects_Full_Code.pdf` (104 pages), read with `pypdf`.
- **How it was read:** every page was extracted to text and searched programmatically
  (`PdfReader(...).pages[i].extract_text()`), then the relevant pages were printed in full.

Reproduce with:

```bash
python - <<'PY'
from pypdf import PdfReader
r = PdfReader(r"C:\Users\<user>\Downloads\101_Python_Mini_Projects_Full_Code.pdf")
print(r.pages[92].extract_text())   # project 90  (printed label: "Page 93")
print(r.pages[73].extract_text())   # project 71  (printed label: "Page 74")
print(r.pages[74].extract_text())   # project 72  (printed label: "Page 75")
PY
```

> **Page-number note.** The brief cites PDF pages 92, 73 and 74 for projects 90, 71 and 72.
> In the file, the printed page label on those sheets belongs to the *previous* project
> (project 71's code sits on the sheet printed "Page 74", project 90's on the sheet printed
> "Page 93"). The project **titles** are unambiguous, so the audit below goes by title.

---

## 0. The most important finding

The PDF does not contain 101 distinct programs. It contains **six short templates cycling in
a fixed six-page rotation**. Searching the extracted text for one distinctive line per
template gives:

| Template | Distinctive line | Pages it appears on |
| --- | --- | --- |
| SQLite CRUD | `CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, title TEXT, status TEXT` | **16** (14, 20, 26, …, 92, 98) |
| Keyword-count search | `score=text.lower().count(query)` | **15** (15, 21, 27, …, 75, 87, 93) |
| CSV column profiler | `Dataset summary` | **15** (18, 24, …, 90, 96) |
| Flask `/items` API | `@app.get("/items")` | **15** (17, 23, …, 89, 95) |
| Recursive file backup | `print("Backup complete.")` | **15** (19, 25, …, 91, 97) |

So the title and the one-line description on a page frequently describe a feature that the
code below it does not implement. That is exactly the trap the brief warned about, and it is
the reason **nothing was copied**: the code on the three named pages implements none of the
RAG functionality this project needed. What follows is the page-by-page audit.

---

## 1. Project 90 — "Document Q&A Assistant"

**Printed label:** Page 93 · **Page index:** 92
**Tagline in the PDF:** *"Chunk local documents and retrieve relevant passages."*

**What the code actually is** (reproduced verbatim from the extracted text):

```python
from pathlib import Path
import json, csv, re
ROOT=Path(".")
query=input("Search term: ").lower()
extensions={".txt",".md",".py",".csv",".json",".html",".js",".css"}
results=[]
for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix.lower() in extensions:
        try: text=p.read_text(errors="ignore")
        except: continue
        score=text.lower().count(query)
        if score:
            results.append((score,p))
for score,p in sorted(results,reverse=True):
    print(f"{score:4}  {p}")
print(f"\nFound {len(results)} matching files.")
```

### What it does have

- `pathlib.Path.rglob("*")` recursive discovery.
- An extension allow-list, normalised with `.suffix.lower()`.
- A guarded read: `try/except` around `p.read_text(errors="ignore")`.
- Case-insensitive matching via `.lower()` on both sides.
- Ranking by descending occurrence count, printed as a flat list.

### What the tagline claims and the code does not do

| Claimed by the tagline | Reality |
| --- | --- |
| "Chunk local documents" | No chunking of any kind. The whole file is one string. |
| "Retrieve relevant passages" | No passages. The unit of output is a **file path**, not a passage. |
| Question answering | There is no question — the program prompts for a *search term*. |
| Embeddings, vector search | Absent. Scoring is `str.count`, a substring count. |

It also cannot read PDFs at all: the extension set is text-ish formats only, so a `.pdf`,
`.docx` or image file is skipped silently. A one-word term like `"a"` scores every file by
raw frequency, which is the opposite of retrieval quality — it has no notion of rarity,
length normalisation or relevance.

### What was reused from it (and how it was improved)

| Idea taken | Where it landed | What changed |
| --- | --- | --- |
| Extension allow-list with lower-cased suffixes | [config.py](../backend/app/core/config.py) (`allowed_extensions`), enforced in [pipeline.py](../backend/app/services/pipeline.py) `check_upload` | Configurable via `ALLOWED_EXTENSIONS`, validated on load, and the extension is additionally **cross-checked against the file's actual bytes** instead of being trusted. |
| Guarded, failure-tolerant file reading | [extraction.py](../backend/app/services/extraction.py) `_decode_text` | Replaced "silently ignore decode errors" with BOM detection and a UTF-8 → cp1252 → latin-1 cascade, so mojibake is fixed rather than discarded. |
| Case-insensitive matching | [text_utils.py](../backend/app/services/text_utils.py) `tokenize` | Case folding is only the first step; tokens are also stop-worded and stemmed. |
| Ranking hits by keyword frequency | [retrieval.py](../backend/app/services/retrieval.py) `LexicalIndex` | Raw `count()` is replaced by **Okapi BM25** (idf weighting, length normalisation, `k1`/`b` saturation), and it is one of *two* scores fused per chunk. |
| `rglob` discovery of local files | Not reused in the app | The upload model is explicit user uploads with a size ceiling — a filesystem crawler is the wrong security posture for a web app. `rglob` is still used where it belongs: in the test suite and `scripts/`. |

---

## 2. Project 71 — "PDF Text Search Engine"

**Printed label:** Page 74 · **Page index:** 73
**Tagline in the PDF:** *"Index PDF text and search across a local collection."*

**What the code actually is** — a SQLite CRUD to-do list:

```python
import sqlite3, json
from datetime import datetime
DB="pdf_text_search_engine.db"
db=sqlite3.connect(DB)
db.execute("CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, title TEXT, status TEXT, "
           "priority INTEGER, created TEXT)")
db.commit()

def add():
    title=input("Title: "); status=input("Status [todo]: ") or "todo"
    priority=int(input("Priority 1-5: ") or 3)
    db.execute("INSERT INTO records(title,status,priority,created) VALUES(?,?,?,?)",
               (title,status,priority,datetime.now().isoformat(timespec="seconds"))); db.commit()

def list_items():
    ...
```

### Audit

- **No PDF library is imported.** No `pypdf`, `pdfplumber`, `PyPDF2`, `fitz`, `pdfminer` — the
  words "pdf" and "search" appear only in the filename `pdf_text_search_engine.db` and the title.
- **No text extraction, no index.** The table stores `title`, `status`, `priority`, `created` —
  to-do metadata, not document text or terms.
- **No search.** The only retrieval is `SELECT id,title,status,priority,created ... ORDER BY
  priority DESC, created DESC` — a listing, not a query.
- The import list (`sqlite3`, `json`, `datetime`) contains nothing related to PDFs.

This template is the most heavily reused one in the PDF: **16 pages** carry it, including
projects 89 ("AI Chat Assistant"), 64, 58, and so on.

### What was used from it

**Only the goal**, as the brief intended: that searching across a *local collection* is a
useful shape. The concrete decisions it informed:

- PDF text is extracted **per page** rather than per file, so page numbers survive into
  citations ([extraction.py](../backend/app/services/extraction.py) `_extract_pdf`, which uses
  `pypdf` page by page). Project 71 has no page concept at all.
- Document metadata (filename, size, sha256, status, timestamps, chunk counts) is persisted in
  **SQLite** ([db.py](../backend/app/storage/db.py)) — the one structural idea the template has.
  The schema, migrations, WAL settings, indexes and concurrency story were written from scratch.

**No code was copied**, because there was nothing relevant to copy.

---

## 3. Project 72 — "OCR Document Pipeline"

**Printed label:** Page 75 · **Page index:** 74
**Tagline in the PDF:** *"OCR image documents and save searchable text."*

**What the code actually is** — byte-for-byte the *same* keyword-count script as project 90:

```python
from pathlib import Path
import json, csv, re
ROOT=Path(".")
query=input("Search term: ").lower()
extensions={".txt",".md",".py",".csv",".json",".html",".js",".css"}
...
                score=text.lower().count(query)
...
```

### Audit

- **No OCR engine.** No `pytesseract`, `tesseract`, `easyocr`, `paddleocr`, `PIL`, `cv2` — no
  image handling of any kind. Its import list is `pathlib`, `json`, `csv`, `re`.
- **No image extensions.** The allow-list is `.txt .md .py .csv .json .html .js .css` — the
  script refuses to look at `.png`, `.jpg`, `.tif` or `.pdf`.
- **Saves nothing.** Despite "save searchable text", the script only prints `(score, path)` to
  stdout. There is no output file, no sidecar text, no database.
- It also contains an unused `import json, csv, re` — `re` is never used, and neither is `json`.
- Verbose-identical to project 90 and to 13 other pages.

### What was used from it

**The idea, deliberately not implemented.** OCR is documented as a non-goal in
the project README, §8 and not claimed anywhere in the UI: scanned PDFs with no text layer
are reported as an extraction failure with an actionable message, not silently answered from
garbage. Adding OCR would mean a heavyweight binary dependency (`tesseract`), a language-data
download, and a multi-second-per-page cost that does not fit the "usable on a CPU-only laptop"
requirement, so it is listed as a future extension rather than faked.

---

## 4. Why nothing else in the PDF could be reused

The six templates are: SQLite CRUD, keyword-count search, CSV profiler, Flask `/items` REST,
CSV summary statistics, and recursive file backup. None of them contains:

- a PDF/text/DOCX **parser**,
- **chunking** with offsets or metadata,
- an **embedding** or vector representation,
- a **vector index** or approximate/exact nearest-neighbour search,
- **ranking** beyond `str.count` or `ORDER BY`,
- **citation** generation,
- **evaluation** of retrieval (recall/precision/MRR),
- a **refusal** path for unanswerable questions.

Every one of those was therefore written from scratch for this project. The mapping is:

| Capability | Written from scratch in |
| --- | --- |
| PDF/TXT/DOCX extraction with page attribution and content sniffing | [extraction.py](../backend/app/services/extraction.py) |
| Sentence-aware chunking with overlap and char offsets | [chunking.py](../backend/app/services/chunking.py) |
| Embeddings (deterministic subword hashing + optional sentence-transformers) | [embeddings.py](../backend/app/services/embeddings.py) |
| Persistent NumPy vector index with atomic saves | [vector_store.py](../backend/app/storage/vector_store.py) |
| Hybrid dense + BM25 retrieval with configurable fusion | [retrieval.py](../backend/app/services/retrieval.py) |
| Extractive, citation-anchored answering with an evidence gate | [answering.py](../backend/app/services/answering.py), [qa.py](../backend/app/services/qa.py) |
| 7-stage pipeline with live progress and verification | [pipeline.py](../backend/app/services/pipeline.py) |
| Retrieval/answer evaluation with auditable ground truth | [evaluation.py](../backend/app/services/evaluation.py) |
| SQLite metadata, conversations, events, eval runs | [db.py](../backend/app/storage/db.py) |

## 5. Credit

The reference PDF earned its place in the design in three concrete ways:

1. **Project 90's file discovery** confirmed the value of a small, explicit extension
   allow-list plus tolerant reading — both are now implemented more strictly (byte-level
   sniffing, decode cascade) and credited above.
2. **Project 90's frequency ranking** is the honest baseline this project had to beat; BM25
   plus dense fusion is the measured answer, and
   [evaluation.py](../backend/app/services/evaluation.py) exists so the claim can be checked
   rather than asserted.
3. **Projects 71 and 72** are the clearest examples of the failure mode the brief named:
   a title promising PDF search or OCR over code that does neither. They shaped this project's
   documentation policy — every capability claim in the project README is tied to a
   command you can run, and unimplemented things (OCR, neural embeddings by default,
   multi-process indexing) are listed as limitations instead of being described as features.
