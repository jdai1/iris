import pytest

from iris.services.common.config import MissingOpenAIKeyError
from iris.services.ingestion import document_classifier
from iris.services.ingestion.extract import extract_page


def test_extract_classifies_substantive_essay():
    html = """
    <html><head><title>Small Teams</title><meta name="author" content="Jane"/></head>
    <body><article><p>Small teams work because coordination costs compound.</p>
    <p>""" + " ".join(["software organizations learn through tight feedback loops"] * 80) + """</p>
    <a href="/next">Next</a></article></body></html>
    """
    page = extract_page(html, "https://example.com/post")
    assert page.document_type == "essay"
    assert page.title == "Small Teams"
    assert page.author == "Jane"
    assert page.links[0].url == "https://example.com/next"


def test_extract_classifies_link_collection():
    links = "".join(f'<li><a href="https://example{i}.com">Link {i}</a></li>' for i in range(12))
    page = extract_page(f"<html><head><title>Reading links</title></head><body><ul>{links}</ul></body></html>", "https://a.test/links")
    assert page.document_type == "collection"


def test_extract_classifies_archive_index_as_collection():
    links = "".join(f'<li><a href="/post-{i}">Post {i}</a> Short teaser text.</li>' for i in range(30))
    page = extract_page(
        f"<html><head><title>Blog archive</title></head><body><main><h1>Archive</h1><ul>{links}</ul></main></body></html>",
        "https://a.test/archive",
    )
    assert page.document_type == "collection"


def test_extract_classifies_about_page_as_profile():
    html = """
    <html><head><title>About Jane</title></head><body><main>
    <p>Jane writes software and studies organizations.</p>
    <p>""" + " ".join(["background research projects contact speaking"] * 60) + """</p>
    </main></body></html>
    """
    page = extract_page(html, "https://a.test/about")
    assert page.document_type == "profile"


def test_extract_classifies_docs_page_as_reference():
    html = """
    <html><head><title>API Reference</title></head><body><main>
    <p>""" + " ".join(["parameter response endpoint object method"] * 100) + """</p>
    </main></body></html>
    """
    page = extract_page(html, "https://a.test/docs/api")
    assert page.document_type == "reference"


def test_extract_ignores_gambling_spam_pages():
    html = """
    <html><head><title>먹튀사이트 검증 뉴스 먹튀케어</title></head><body><main>
    <p>안전한 온라인 베팅을 위한 먹튀검증 커뮤니티와 카지노사이트 정보를 제공합니다.</p>
    <p>""" + " ".join(["카지노 먹튀 토토 안전놀이터 검증 플랫폼"] * 80) + """</p>
    </main></body></html>
    """
    page = extract_page(html, "https://rationalconspiracy.com/spam")
    assert page.document_type == "ignore"


def test_extract_ignores_non_english_pages():
    html = """
    <html><head><title>מאמר בעברית</title></head><body><main>
    <p>זהו טקסט בעברית שמייצג מאמר ארוך שאינו באנגלית.</p>
    <p>""" + " ".join(["אנחנו לא רוצים להכניס מקורות שאינם באנגלית לקורפוס בשלב הזה"] * 80) + """</p>
    </main></body></html>
    """
    page = extract_page(html, "https://example.com/hebrew")
    assert page.document_type == "ignore"


def test_extract_can_use_llm_for_ambiguous_documents(monkeypatch):
    monkeypatch.setattr(document_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        document_classifier,
        "_classify_document_with_llm",
        lambda **_kwargs: document_classifier.DocumentClassification(
            document_type="collection",
            confidence=0.91,
            reason="LLM saw this as an anthology/index page.",
        ),
    )
    html = """
    <html><head><title>Selected Notes</title></head><body><main>
    <p>""" + " ".join(["A short editorial note about a group of readings and collected arguments."] * 50) + """</p>
    </main></body></html>
    """

    page = extract_page(html, "https://example.com/selected-notes")

    assert page.document_type == "collection"


def test_ambiguous_document_llm_requires_openai_key(monkeypatch):
    def missing_key(_feature):
        raise MissingOpenAIKeyError("missing test key")

    monkeypatch.setattr(document_classifier, "require_openai_api_key", missing_key)
    html = """
    <html><head><title>Selected Notes</title></head><body><main>
    <p>""" + " ".join(["A short editorial note about a group of readings and collected arguments."] * 50) + """</p>
    </main></body></html>
    """

    with pytest.raises(MissingOpenAIKeyError):
        extract_page(html, "https://example.com/selected-notes")
