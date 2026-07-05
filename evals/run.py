from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from iris.dao import db  # noqa: E402
from iris.dao import search as search_dao  # noqa: E402
from iris.schemas.retrieval import RankedDocument  # noqa: E402
from iris.services.retrieval.search import search_documents, synthesize_answer  # noqa: E402


DEFAULT_QUESTIONS_PATH = ROOT_DIR / "evals" / "questions.jsonl"
DEFAULT_REPORTS_DIR = ROOT_DIR / "evals" / "reports"

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "because",
    "become",
    "before",
    "being",
    "better",
    "between",
    "could",
    "design",
    "does",
    "from",
    "have",
    "into",
    "make",
    "most",
    "people",
    "should",
    "that",
    "their",
    "there",
    "these",
    "thing",
    "think",
    "through",
    "want",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    domain: str
    query: str
    intent: str
    tags: list[str]
    difficulty: str = "specific"
    must_have_terms: list[str] | None = None
    expected_results: list[dict[str, object]] | None = None


@dataclass(frozen=True)
class EvalMetrics:
    result_count: int
    top_score: float
    top3_average_score: float
    query_term_coverage: float
    top_result_coverage: float
    top5_source_count: int
    has_substantive_summary: bool
    expected_match_count: int = 0
    expected_top_rank: int | None = None


@dataclass(frozen=True)
class EvalResult:
    question: EvalQuestion
    verdict: str
    metrics: EvalMetrics
    answer: str
    results: list[dict[str, object]]


def load_questions(path: Path) -> list[EvalQuestion]:
    questions: list[EvalQuestion] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            raw = json.loads(stripped)
            missing = {"id", "domain", "query", "intent", "tags"} - set(raw)
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise ValueError(f"{path}:{line_number} missing fields: {missing_text}")
            tags = raw["tags"]
            if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
                raise ValueError(f"{path}:{line_number} tags must be a list of strings")
            questions.append(
                EvalQuestion(
                    id=str(raw["id"]),
                    domain=str(raw["domain"]),
                    query=str(raw["query"]),
                    intent=str(raw["intent"]),
                    tags=tags,
                    difficulty=str(raw.get("difficulty", "specific")),
                    must_have_terms=list(raw["must_have_terms"]) if raw.get("must_have_terms") else None,
                    expected_results=list(raw["expected_results"]) if raw.get("expected_results") else None,
                )
            )
    return questions


def evaluate_question(question: EvalQuestion, *, limit: int) -> EvalResult:
    _search_row, ranked = search_documents(question.query, limit=limit, persist=False)
    metrics = score_results(question, ranked)
    verdict = verdict_for_metrics(metrics)
    return EvalResult(
        question=question,
        verdict=verdict,
        metrics=metrics,
        answer=synthesize_answer(question.query, ranked),
        results=[serialize_result(row) for row in ranked],
    )


def disable_pgvector_search() -> None:
    """Force retrieval through the portable in-process scorer.

    This is useful for local smoke evals when the Postgres corpus stores
    OpenAI-sized vectors but the current process is using the 96-dimensional
    local embedding fallback.
    """

    def _portable_only(_query_vector: list[float], *, limit: int, exclude_document_id: int | None = None):
        return []

    search_dao.vector_search_documents = _portable_only


def score_results(question: EvalQuestion, ranked: list[RankedDocument]) -> EvalMetrics:
    if not ranked:
        return EvalMetrics(
            result_count=0,
            top_score=0.0,
            top3_average_score=0.0,
            query_term_coverage=0.0,
            top_result_coverage=0.0,
            top5_source_count=0,
            has_substantive_summary=False,
            **expected_result_metrics(question, ranked),
        )

    top3 = ranked[:3]
    top5 = ranked[:5]
    terms = set(question.must_have_terms or normalized_terms(question.query))
    coverage = query_term_coverage(terms, top3)
    top_result_coverage = query_term_coverage(terms, ranked[:1])
    summaries = [(row.document.summary or "").strip() for row in top3]
    return EvalMetrics(
        result_count=len(ranked),
        top_score=round(float(ranked[0].score), 4),
        top3_average_score=round(sum(float(row.score) for row in top3) / len(top3), 4),
        query_term_coverage=round(coverage, 4),
        top_result_coverage=round(top_result_coverage, 4),
        top5_source_count=len({row.document.source.canonical_domain for row in top5}),
        has_substantive_summary=any(len(summary) >= 80 for summary in summaries),
        **expected_result_metrics(question, ranked),
    )


def expected_result_metrics(question: EvalQuestion, ranked: list[RankedDocument]) -> dict[str, int | None]:
    expected = question.expected_results or []
    expected_ids = {
        int(row["document_id"])
        for row in expected
        if isinstance(row, dict) and row.get("document_id") is not None
    }
    if not expected_ids:
        return {"expected_match_count": 0, "expected_top_rank": None}

    matched_ranks = [
        index
        for index, row in enumerate(ranked, start=1)
        if row.document.id in expected_ids
    ]
    return {
        "expected_match_count": len(matched_ranks),
        "expected_top_rank": min(matched_ranks) if matched_ranks else None,
    }


def verdict_for_metrics(metrics: EvalMetrics) -> str:
    if metrics.result_count == 0:
        return "no_results"
    if (
        metrics.top_score >= 0.42
        and metrics.query_term_coverage >= 0.28
        and metrics.top_result_coverage >= 0.35
        and metrics.has_substantive_summary
    ):
        return "strong"
    if metrics.top_score >= 0.6 and metrics.top_result_coverage >= 0.25 and metrics.has_substantive_summary:
        return "strong"
    if metrics.top_score >= 0.22 and (metrics.query_term_coverage >= 0.18 or metrics.top_result_coverage >= 0.18):
        return "partial"
    return "weak"


def normalized_terms(text: str) -> list[str]:
    terms = []
    for term in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text.lower()):
        if term in STOPWORDS:
            continue
        terms.append(term)
    return sorted(set(terms))


def query_term_coverage(terms: set[str], ranked: list[RankedDocument]) -> float:
    if not terms:
        return 0.0
    haystack = "\n".join(document_evidence_text(row) for row in ranked).lower()
    hits = sum(1 for term in terms if term.lower() in haystack)
    return hits / len(terms)


def document_evidence_text(row: RankedDocument) -> str:
    document = row.document
    return " ".join(
        item
        for item in [
            document.title or "",
            document.author or "",
            document.source.canonical_domain,
            document.summary or "",
            " ".join(document.topics or []),
        ]
        if item
    )


def serialize_result(row: RankedDocument) -> dict[str, object]:
    document = row.document
    return {
        "document_id": document.id,
        "title": document.title or document.url,
        "source": document.source.canonical_domain,
        "url": document.url,
        "score": round(float(row.score), 4),
        "reason": row.reason,
        "summary": (document.summary or "").strip(),
        "topics": document.topics or [],
    }


def select_questions(
    questions: Iterable[EvalQuestion],
    *,
    domains: set[str],
    sample_per_domain: int | None,
    max_questions: int | None,
) -> list[EvalQuestion]:
    selected = [question for question in questions if not domains or question.domain in domains]
    if sample_per_domain is not None:
        by_domain: dict[str, list[EvalQuestion]] = {}
        for question in selected:
            by_domain.setdefault(question.domain, []).append(question)
        selected = []
        for domain in sorted(by_domain):
            selected.extend(by_domain[domain][:sample_per_domain])
    if max_questions is not None:
        selected = selected[:max_questions]
    return selected


def render_markdown(results: list[EvalResult], *, questions_path: Path, limit: int) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Iris Search Eval Report",
        "",
        f"- Generated: {generated_at}",
        f"- Questions: `{questions_path}`",
        f"- Result limit: {limit}",
        f"- Total questions: {len(results)}",
        "",
    ]
    lines.extend(render_summary(results))
    lines.extend(render_domain_summary(results))
    lines.extend(render_question_table(results))
    lines.extend(render_backlog(results))
    lines.extend(render_details(results))
    return "\n".join(lines).rstrip() + "\n"


def render_summary(results: list[EvalResult]) -> list[str]:
    counts = verdict_counts(results)
    total = max(1, len(results))
    return [
        "## Summary",
        "",
        f"- Strong: {counts.get('strong', 0)} ({counts.get('strong', 0) / total:.0%})",
        f"- Partial: {counts.get('partial', 0)} ({counts.get('partial', 0) / total:.0%})",
        f"- Weak: {counts.get('weak', 0)} ({counts.get('weak', 0) / total:.0%})",
        f"- No results: {counts.get('no_results', 0)} ({counts.get('no_results', 0) / total:.0%})",
        "",
    ]


def render_domain_summary(results: list[EvalResult]) -> list[str]:
    by_domain: dict[str, list[EvalResult]] = {}
    for result in results:
        by_domain.setdefault(result.question.domain, []).append(result)
    lines = [
        "## Domains",
        "",
        "| Domain | Questions | Strong | Partial | Weak | No results |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for domain in sorted(by_domain):
        rows = by_domain[domain]
        counts = verdict_counts(rows)
        lines.append(
            f"| {domain} | {len(rows)} | {counts.get('strong', 0)} | "
            f"{counts.get('partial', 0)} | {counts.get('weak', 0)} | {counts.get('no_results', 0)} |"
        )
    lines.append("")
    return lines


def render_question_table(results: list[EvalResult]) -> list[str]:
    lines = [
        "## Question Results",
        "",
        "| ID | Domain | Verdict | Expected rank | Top score | Coverage | Top coverage | Top hit |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        top_hit = result.results[0]["title"] if result.results else ""
        lines.append(
            f"| {result.question.id} | {result.question.domain} | {result.verdict} | "
            f"{result.metrics.expected_top_rank or ''} | "
            f"{result.metrics.top_score:.3f} | {result.metrics.query_term_coverage:.0%} | "
            f"{result.metrics.top_result_coverage:.0%} | {escape_cell(str(top_hit))} |"
        )
    lines.append("")
    return lines


def render_backlog(results: list[EvalResult]) -> list[str]:
    backlog = [result for result in results if result.verdict in {"weak", "no_results"}]
    if not backlog:
        return []
    lines = [
        "## Corpus Backlog",
        "",
        "These are the weakest current-answer areas. They are good candidates for targeted source discovery or manual curation.",
        "",
    ]
    for result in backlog:
        lines.append(f"- `{result.question.id}` {result.question.query}")
    lines.append("")
    return lines


def render_details(results: list[EvalResult]) -> list[str]:
    lines = ["## Details", ""]
    for result in results:
        lines.extend(
            [
                f"### {result.question.id}: {result.question.query}",
                "",
                f"- Domain: {result.question.domain}",
                f"- Intent: {result.question.intent}",
                f"- Verdict: {result.verdict}",
                (
                    f"- Metrics: top_score={result.metrics.top_score:.3f}, "
                    f"top3_avg={result.metrics.top3_average_score:.3f}, "
                    f"coverage={result.metrics.query_term_coverage:.0%}, "
                    f"top_coverage={result.metrics.top_result_coverage:.0%}, "
                    f"sources_top5={result.metrics.top5_source_count}, "
                    f"expected_matches={result.metrics.expected_match_count}, "
                    f"expected_top_rank={result.metrics.expected_top_rank or 'none'}"
                ),
                "",
            ]
        )
        if result.question.expected_results:
            lines.append("Expected results:")
            for expected in result.question.expected_results:
                lines.append(
                    f"- {expected.get('title')} ({expected.get('source')})"
                    f" document_id={expected.get('document_id')}"
                )
            lines.append("")
        if result.answer:
            lines.extend(["Answer preview:", "", result.answer, ""])
        if not result.results:
            lines.extend(["No results.", ""])
            continue
        lines.append("Top results:")
        for index, row in enumerate(result.results[:5], start=1):
            summary = str(row.get("summary") or "").replace("\n", " ")[:260]
            lines.extend(
                [
                    f"{index}. {row['title']} ({row['source']})",
                    f"   score={row['score']} reason={row['reason']}",
                    f"   {row['url']}",
                ]
            )
            if summary:
                lines.append(f"   {summary}")
        lines.append("")
    return lines


def verdict_counts(results: Iterable[EvalResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    return counts


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_jsonl(path: Path, results: list[EvalResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Iris corpus search evals.")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--domain", action="append", default=[], help="Run only one domain. Can be repeated.")
    parser.add_argument("--limit", type=int, default=8, help="Search result limit per question.")
    parser.add_argument("--sample-per-domain", type=int, default=None)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument(
        "--disable-pgvector",
        action="store_true",
        help="Use portable scoring instead of Postgres pgvector search.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Write a markdown report.")
    parser.add_argument("--json-out", type=Path, default=None, help="Write machine-readable JSONL results.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    questions = select_questions(
        load_questions(args.questions),
        domains=set(args.domain),
        sample_per_domain=args.sample_per_domain,
        max_questions=args.max_questions,
    )
    if not questions:
        raise SystemExit("No questions selected.")

    if args.disable_pgvector:
        disable_pgvector_search()

    with db.session_scope():
        results = [evaluate_question(question, limit=args.limit) for question in questions]

    report = render_markdown(results, questions_path=args.questions, limit=args.limit)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.json_out, results)
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
