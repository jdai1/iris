# Iris Next Plan

Focus: corpus quality, autopilot crawling, and hybrid search. UX cleanup comes later.

## 1. Harden Essay Detection

Reader-facing documents should be substantive standalone essays, not archives, tags, about pages, product pages, docs, or link dumps.

Document types:

- `essay`: authored prose with original argument, reflection, explanation, or opinion.
- `collection`: archive pages, tag pages, reading lists, blogrolls, link roundups, index pages.
- `profile`: about pages, author bios, project/contact pages.
- `reference`: docs, APIs, encyclopedic/reference pages.
- `ignore`: short/empty/media/commercial/error/duplicate pages.

Signals:

- URL/path: `/tag/`, `/category/`, `/archive`, `/posts`, `/about`, `/privacy`, query-heavy URLs.
- DOM: article/main presence, paragraph count, heading density, list density, text-to-link ratio.
- Content: word count, sentence count, title markers, argument/prose markers.
- Metadata: author, published date, article OpenGraph metadata, RSS item membership.
- Deduping: canonical URL, content hash, near-duplicate title/content.

Build:

1. Add `essay_classifier.py` returning type, quality, confidence, reason.
2. Deterministic rules first for obvious cases.
3. Optional cheap LLM only for ambiguous pages.
4. Add fixtures for essay/archive/tag/about/link roundup/docs/product/short note.
5. Add audit and reclassification CLI commands.

Acceptance:

- Search/digest only surface `essay`.
- Fixture crawls do not surface archives/tag pages.
- Ben Kuhn keeps actual essays and demotes `/posts`, `/tag/*`, `/writing`, etc.

## 2. Autopilot Crawl Policy

Queued sources should be crawled by priority, not FIFO.

Priority formula:

```text
priority =
  0.45 * log(1 + inbound_link_count_from_indexed_docs)
+ 0.20 * log(1 + distinct_referring_sources)
+ 0.15 * source_classifier_confidence_if_known
+ 0.10 * overlap_with_user_interests
+ 0.05 * recency_or_feed_presence
+ 0.05 * manual_seed_bonus
- 0.25 * ignored_or_failed_penalty
- 0.15 * broad_platform_penalty
```

Autopilot command:

```bash
iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --embed --dry-run
iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --embed
```

Loop:

1. Compute source priorities.
2. Print top planned sources and reasons.
3. For each source, classify homepage.
4. If accepted, crawl bounded pages.
5. Classify/store documents and links.
6. Optionally embed accepted essays.
7. Print DB deltas and cost estimates.

Guardrails:

- Never crawl ignored sources unless forced.
- Shallow default depth for autopilot.
- Per-source page caps.
- Per-run OpenAI call caps.
- Dry-run mode.
- Resumable through source statuses and crawl jobs.

## 3. Hybrid Search

Embeddings are probably worth it once the corpus grows, but should be cost-controlled.

Policy:

- Embed accepted essays only.
- Do not embed collections, profiles, ignored pages, or source homepages.
- Batch embeddings explicitly.
- Track embedding model/version in a later schema cleanup.

Retrieval:

1. Candidate generation from lexical score, embedding cosine, graph score, and feedback.
2. Merge top K from each retrieval path.
3. Rerank deterministically first.
4. Optional LLM reranker over top 20-40.
5. Later: LLM answer synthesis with citations.

Initial formula:

```text
score =
  0.30 * lexical_score
+ 0.35 * embedding_score
+ 0.15 * document_quality
+ 0.10 * graph_authority
+ 0.10 * feedback_affinity
```

## 4. Immediate Build Order

1. `source-priorities` CLI. Done.
2. `audit-documents` CLI. Done.
3. Stronger deterministic essay classifier. Initial version done.
4. Existing document reclassification. Done.
5. `autopilot --dry-run`. Done.
6. Real autopilot with budgets. Initial version done.
7. Controlled top-clout crawl batch. Done.
8. Batch embed accepted essays. Done for current corpus.
9. Improve hybrid search candidate generation and optional reranking.

## 5. Implemented Autopilot Surface

Commands:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m iris.cli source-priorities --limit 20
PYTHONPATH=backend backend/.venv/bin/python -m iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --max-documents-per-source 40 --skip-existing --dry-run
PYTHONPATH=backend backend/.venv/bin/python -m iris.cli autopilot --budget-sources 20 --max-pages 80 --max-depth 2 --max-documents-per-source 40 --skip-existing
PYTHONPATH=backend backend/.venv/bin/python -m iris.cli index-runs --limit 10
PYTHONPATH=backend backend/.venv/bin/python -m iris.cli index-events <run_id>
```

Telemetry:

- `index_runs`: one row per autopilot/indexing batch.
- `index_events`: plan, source start, source homepage normalization, source finish.
- `crawl_jobs`: still one row per source crawl.

Current behavior:

- Sources are selected by clout-style priority from inbound links from indexed essays and distinct referring sources.
- Autopilot normalizes domain-level source homepages to the domain root before classification/crawl.
- Source start events are committed before long crawls, so interrupted runs leave a trace.
- Each source finishes with page/doc/link/discovery counters in event payload.
- `--skip-existing` resumes source crawls by skipping already-fetched document URLs without spending page budget.
- `--max-documents-per-source` caps accepted essay documents separately from fetched pages.
- Autopilot embeds by default; use `--no-embed` to disable embedding for a run.

Next robustness improvements:

- Add stale run recovery for runs interrupted mid-source.
- Add per-run OpenAI call/cost counters.
- Add source retry backoff and failure class labels.
- Add document audit/reclassification before broad crawling.

## 6. Completed Validation Pass

Implemented:

- `document_classifier.py` with `essay`, `collection`, `profile`, `reference`, and `ignore`.
- `audit-documents` and `reclassify-documents`.
- Content-link-based classification during extraction, so site chrome links do not demote real posts.
- Source classifier prompt tightened to accept personal blogs and messy personal archives.
- OpenAI embeddings applied to the current accepted essay corpus.
- Local `.env` enables `IRIS_USE_OPENAI_EMBEDDINGS=1` so API/FE query embeddings match stored vectors.

Validated:

- Tests: `17 passed`.
- Frontend build passes.
- DB after validation: 576 sources, 106 documents.
- Reclassification reduced reader-facing pollution while keeping essays searchable.
- Controlled autopilot:
  - Daring Fireball and LessWrong were rejected/skipped with telemetry.
  - Paul Graham indexed 3 essays.
  - JeffTK indexed 3 posts after source/document classifier fixes.
- Search with OpenAI embeddings:
  - `startup equity` returns Ben Kuhn stock/equity essays.
  - `AI vulnerability cultures` returns the JeffTK article first.

Remaining gaps before long unattended runs:

- Track OpenAI calls/cost in `index_runs`/`index_events`.
- Add stale run recovery and retry/backoff.
- Add an LLM document classifier only for ambiguous pages.
- Clean extracted text better for sites with custom page chrome.
- Move embedding model/version into schema before productionizing.
