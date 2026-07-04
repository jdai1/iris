# Iris Evals

This folder benchmarks whether the current Iris corpus can answer specific, niche user questions. The goal is dataset quality: find the domains where search already returns useful essays and the domains where the corpus needs targeted expansion.

## Question Bank

`datasets/questions.jsonl` is the seed eval set. Each row has:

- `id`: stable question id
- `domain`: broad user-intent area
- `query`: the user question to search
- `tags`: facets for later slicing
- `difficulty`: usually `specific` or `niche`
- `must_have_terms`: optional terms used for coverage scoring instead of terms inferred from the query
- `expected_results`: optional golden targets for corpus-first questions. Each target should include at least `document_id`, and should usually include `title`, `source`, and `url` for easy review.
- `intent`: optional note for broad, intent-first evals. Golden rows generally omit it.

Keep adding real user questions here. Prefer concrete, high-intent phrasing over generic keywords.

`datasets/golden_questions.jsonl` is the corpus-first regression set. These
questions were written after looking at the current indexed blogs, so each row
says which specific article should appear. Use it to catch regressions in
retrieval quality and to tune the LLM judge against human expectations.

`datasets/golden_natural_questions.jsonl` uses the same expected target
documents, but rewrites queries into less title-matched, more natural user
phrasing. Use it to check whether retrieval still works when the user does not
know the article's exact vocabulary.

## Run

Use the backend Python environment, not system Python 3.9.

```bash
cd /Users/jdai/.codex/worktrees/3017/iris
DATABASE_URL=postgresql://postgres:1234@localhost:5432/iris \
IRIS_USE_OPENAI_EMBEDDINGS=1 \
PYTHONPATH=backend \
backend/.venv/bin/python evals/run.py \
  --out evals/reports/latest.md \
  --json-out evals/reports/latest.jsonl
```

If your Postgres corpus has 1536-dimensional OpenAI embeddings but this process
does not have `IRIS_USE_OPENAI_EMBEDDINGS=1`, run a cheap keyword/local smoke
benchmark with portable scoring:

```bash
DATABASE_URL=postgresql://postgres:1234@localhost:5432/iris \
PYTHONPATH=backend \
backend/.venv/bin/python evals/run.py \
  --disable-pgvector \
  --sample-per-domain 1 \
  --out evals/reports/smoke.md
```

Useful slices:

```bash
backend/.venv/bin/python evals/run.py --domain career --domain relationships --out evals/reports/career-relationships.md
backend/.venv/bin/python evals/run.py --sample-per-domain 2 --out evals/reports/smoke.md
backend/.venv/bin/python evals/run.py --questions evals/datasets/golden_questions.jsonl --out evals/reports/golden.md --json-out evals/reports/golden.jsonl
backend/.venv/bin/python evals/run.py --questions evals/datasets/golden_natural_questions.jsonl --out evals/reports/golden_natural.md --json-out evals/reports/golden_natural.jsonl
```

## Verdicts

The first-pass grader is deterministic and intentionally simple:

- `strong`: high top result score, meaningful query-term coverage, and at least one substantive summary
- `partial`: something plausibly relevant exists, but answer quality or coverage is suspect
- `weak`: search returns cards, but the evidence looks thin
- `no_results`: nothing cleared the retrieval threshold

Use weak and no-result rows as the corpus acquisition backlog. Strong rows are not a guarantee of answer quality; they are candidates for manual review and future gold-set labeling.

## Next Evals To Add

- LLM judge mode that grades answer helpfulness, citation fit, and hallucination risk.
- Gold document ids for recurring canonical questions once we know the corpus well.
- Source acquisition evals: given weak domains, recommend new blogs/books/authors to crawl.
- Regression gates for a small smoke set that must stay strong before shipping.
