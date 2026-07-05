from __future__ import annotations

import json

from iris.dao.documents import upsert_document
from iris.dao.sources import get_or_create_source
from iris.services.ingestion.embedding import document_embedding_text, dumps_embedding, embed_text

from evals.run import EvalQuestion, evaluate_question, load_questions, normalized_terms, score_results


def add_eval_doc(source, title: str, text: str, topics: list[str]):
    embedding_text = document_embedding_text(
        title=title,
        summary=text[:240],
        topics=topics,
        extracted_text=text,
    )
    return upsert_document(
        source=source,
        url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author="Test Author",
        published_at=None,
        extracted_text=text,
        summary=text[:240],
        topics=topics,
        embedding=dumps_embedding(embed_text(embedding_text)),
        content_hash=title,
    )


def test_load_questions_validates_jsonl(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "career_001",
                "domain": "career",
                "query": "what should I look for in a new job?",
                "intent": "choose a job with better long-term fit",
                "tags": ["career", "decision"],
                "expected_results": [{"document_id": 123, "title": "Expected Essay"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    questions = load_questions(path)

    assert len(questions) == 1
    assert questions[0].id == "career_001"
    assert questions[0].domain == "career"
    assert questions[0].expected_results == [{"document_id": 123, "title": "Expected Essay"}]


def test_normalized_terms_removes_low_signal_words():
    assert "should" not in normalized_terms("what should I look for in a new job?")
    assert "job" in normalized_terms("what should I look for in a new job?")


def test_evaluate_question_returns_ranked_results(session):
    source = get_or_create_source("https://interviews.test", status="indexed")
    add_eval_doc(
        source,
        "Designing Technical Interviews",
        "A strong technical interview measures realistic engineering judgment, communication, debugging, and tradeoffs.",
        ["hiring", "interviews", "engineering"],
    )
    add_eval_doc(
        source,
        "Fermentation Notes",
        "Vegetables, salt, jars, and kitchen experiments.",
        ["cooking"],
    )

    result = evaluate_question(
        EvalQuestion(
            id="hiring_001",
            domain="hiring",
            query="how do I design a technical interview?",
            intent="build a fair engineering interview loop",
            tags=["hiring", "engineering"],
        ),
        limit=3,
    )

    assert result.results
    assert result.results[0]["title"] == "Designing Technical Interviews"
    assert result.verdict in {"strong", "partial"}


def test_score_results_tracks_expected_document_rank(session):
    source = get_or_create_source("https://golden.test", status="indexed")
    expected_doc = add_eval_doc(
        source,
        "Golden Target",
        "A focused essay about debugging production incidents with logs, traces, and concrete hypotheses.",
        ["debugging", "observability"],
    )
    other_doc = add_eval_doc(
        source,
        "Other Target",
        "A focused essay about debugging production incidents with logs, traces, and concrete hypotheses.",
        ["debugging", "observability"],
    )

    result = evaluate_question(
        EvalQuestion(
            id="golden_001",
            domain="engineering",
            query="how do I debug production incidents with logs and traces?",
            intent="retrieve expected debugging essay",
            tags=["engineering", "debugging"],
            expected_results=[{"document_id": expected_doc.id}],
        ),
        limit=5,
    )

    metrics = score_results(
        EvalQuestion(
            id="golden_001",
            domain="engineering",
            query="debugging production incidents logs traces",
            intent="retrieve expected debugging essay",
            tags=["engineering", "debugging"],
            expected_results=[{"document_id": other_doc.id}],
        ),
        [],
    )

    assert result.metrics.expected_match_count == 1
    assert result.metrics.expected_top_rank is not None
    assert metrics.expected_match_count == 0
    assert metrics.expected_top_rank is None
