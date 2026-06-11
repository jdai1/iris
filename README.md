# Iris

Local-first search and digest over a self-growing corpus of substantive blogs and essays.

## Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m iris.cli init-db
.venv/bin/python -m uvicorn iris.api:app --reload --host 127.0.0.1 --port 8000
```

The app reads `DATABASE_URL` first, then `DEV_DATABASE_URL`, then falls back to `sqlite:///backend/iris.db`.
Source classification uses `OPENAI_API_KEY` with `IRIS_SOURCE_CLASSIFIER_MODEL` defaulting to `gpt-4.1-nano`.
OpenAI document embeddings and LLM reranking are opt-in through `IRIS_USE_OPENAI_EMBEDDINGS=1` and `IRIS_USE_LLM_RERANKER=1`.

Useful CLI commands:

```bash
.venv/bin/python -m iris.cli seed https://example.com
.venv/bin/python -m iris.cli crawl https://example.com --max-pages 50 --max-depth 3
.venv/bin/python -m iris.cli classify-source https://example.com
.venv/bin/python -m iris.cli classify-sources --limit 25
.venv/bin/python -m iris.cli ignore-source example.com --delete-rows
.venv/bin/python -m iris.cli audit-documents --limit 30 --verbose
.venv/bin/python -m iris.cli reclassify-documents --dry-run
.venv/bin/python -m iris.cli embed-documents --limit 100 --openai
.venv/bin/python -m iris.cli source-priorities --limit 20
.venv/bin/python -m iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --max-documents-per-source 40 --skip-existing --dry-run
.venv/bin/python -m iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --max-documents-per-source 40 --skip-existing
.venv/bin/python -m iris.cli index-runs --limit 10
.venv/bin/python -m iris.cli index-events 1
.venv/bin/python -m iris.cli search "small teams"
.venv/bin/python -m iris.cli digest --populate
.venv/bin/python -m iris.cli status
.venv/bin/python -m iris.cli sql "select status, count(*) from sources group by status"
```

For Postgres monitoring, use `psql "$DATABASE_URL"` or the connection string in `backend/.env`.

Autopilot writes one `index_runs` row per indexing batch and `index_events` rows for the plan and each source attempt. `crawl_jobs` remains the per-source crawl record.
`max-pages` is a fetched-page budget. `max-documents-per-source` is an accepted-essay budget. `--skip-existing` skips already-fetched document URLs, including HTTP/HTTPS redirect variants, without spending page budget. Autopilot embeds accepted essays by default; use `--no-embed` to skip embedding.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` unless `VITE_API_BASE` is set.

## Validation

```bash
backend/.venv/bin/python -m pytest backend
npm --prefix frontend run build
```
