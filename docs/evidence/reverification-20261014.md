# Re-verification — 2026-10-14

Every command below was executed in this workspace on 2026-10-14 (Windows, Git Bash) against the
code as it stands on disk. Exit status is the real status of the tested command, captured with
`PIPESTATUS[0]` after output filtering — not the status of the filter.

Environment: Python 3.13.5 (`backend/.venv`), Node v22.23.3, npm 10.9.9
(the portable Node install at `%LOCALAPPDATA%\node-portable` was added to `PATH`).

## Commands and results

| # | Command | Observed output | Exit |
| --- | --- | --- | --- |
| 1 | `cd backend && ./.venv/Scripts/python.exe -m pytest` | `194 passed in 16.73s` | 0 |
| 2 | `cd frontend && npm run typecheck` (`tsc --noEmit`) | no output | 0 |
| 3 | `cd frontend && npm run lint` (`eslint . --max-warnings 0`) | no output | 0 |
| 4 | `cd frontend && npm test` | `Test Files 6 passed (6)` / `Tests 66 passed (66)` | 0 |
| 5 | `cd frontend && npm run build` | `dist/assets/index-*.js 261.78 kB │ gzip: 81.48 kB` · `index-*.css 18.83 kB` · `✓ built in 1.60s` | 0 |
| 6 | `python scripts/e2e_check.py --base-url http://127.0.0.1:8000` | `59/59 checks passed` | 0 |
| 7 | `python scripts/measure_evidence_gate.py` | `in-scope answered: 9/9` · `out-of-scope refused: 5/5` · report written to `eval/results/evidence_gate_20261014T153206.json` | 0 |
| 8 | `cd frontend && npm run test:e2e` (Playwright, Chromium, real servers) | `7 passed (43.7s)` | 0 |
| 9 | `POST /api/v1/evaluation/run {"dataset":"synthetic_galaxy","top_k":5}` | `run_id: eval_20261014T153333` · `sample_count: 18` · `recall_at_k: 1.0` · `mrr: 1.0` · `citation_hit_rate: 1.0` · `answer_rate: 1.0` · `precision_at_k: 0.244` · `mean_latency_ms: 3.692` | 0 |
| 10 | `node scripts/verify-readme-links.mjs` | `internal markdown file links checked: true \| scanned: 10 \| missing: 0` | 0 |
| 11 | Secret scan of `README.md`, `docs/`, `BUILD_PROGRESS.md`, `.env.example` for key-shaped strings | no matches | 0 |

## Servers used for the live checks (verified listening)

- Backend: `127.0.0.1:8000`, PID 6236 — `GET /api/v1/health` returned `status: ok`,
  `embedding_provider: hashing-subword-v1`, `answer_provider: extractive`,
  `data_dir: C:\Users\<user>\Desktop\rag-document-intelligence\backend\data-verify`.
- Frontend: `127.0.0.1:5173`, PID 25984 (Vite dev server, proxies `/api` to the backend).

## What this run does and does not prove

- It re-proves every number quoted in README §5 ("Verified on a real machine") and the
  BUILD_PROGRESS status table, from scratch, on 2026-10-14.
- It does **not** prove anything about the optional `sentence` embedding provider or the
  `openai_compatible` answer provider: neither was exercised here (no model download, no key),
  and both remain documented as unverified.
- It does **not** constitute a GitHub Actions run. The workflow file exists but has not executed
  on GitHub; these are the same commands run locally.
