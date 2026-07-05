import pytest

from iris.services.common.config import MissingOpenAIKeyError
from iris.services.ingestion import document_classifier
from iris.services.ingestion.extract import extract_page


def stub_document_llm(
    monkeypatch,
    document_type: str,
    *,
    title: str | None = None,
    summary: str = "LLM summary.",
    topics: list[str] | None = None,
):
    monkeypatch.setattr(document_classifier, "require_openai_api_key", lambda _feature: "test-key")

    def fake_analysis(**kwargs):
        return document_classifier.DocumentAnalysis(
            title=title if title is not None else kwargs.get("metadata_title"),
            summary=summary,
            topics=topics or ["software", "organizations"],
            category_slug="software",
            document_type=document_type,
        )

    monkeypatch.setattr(
        document_classifier,
        "_analyze_document_with_llm",
        fake_analysis,
    )


def test_extract_classifies_substantive_essay(monkeypatch):
    stub_document_llm(monkeypatch, "essay", title="Small Teams", summary="Small teams reduce coordination costs.", topics=["teams"])
    html = """
    <html><head><title>Small Teams</title><meta name="author" content="Jane"/></head>
    <body><article><p>Small teams work because coordination costs compound.</p>
    <p>""" + " ".join(["software organizations learn through tight feedback loops"] * 80) + """</p>
    <a href="/next">Next</a></article></body></html>
    """
    page = extract_page(html, "https://example.com/post")
    assert page.document_type == "essay"
    assert page.title == "Small Teams"
    assert page.summary == "Small teams reduce coordination costs."
    assert page.topics == ["teams"]
    assert page.category_slug == "software"
    assert page.author == "Jane"
    assert page.links[0].url == "https://example.com/next"


def test_extract_classifies_link_collection(monkeypatch):
    stub_document_llm(monkeypatch, "collection")
    links = "".join(f'<li><a href="https://example{i}.com">Link {i}</a></li>' for i in range(12))
    page = extract_page(f"<html><head><title>Reading links</title></head><body><ul>{links}</ul></body></html>", "https://a.test/links")
    assert page.document_type == "collection"


def test_extract_classifies_archive_index_as_collection(monkeypatch):
    stub_document_llm(monkeypatch, "collection")
    links = "".join(f'<li><a href="/post-{i}">Post {i}</a> Short teaser text.</li>' for i in range(30))
    page = extract_page(
        f"<html><head><title>Blog archive</title></head><body><main><h1>Archive</h1><ul>{links}</ul></main></body></html>",
        "https://a.test/archive",
    )
    assert page.document_type == "collection"


def test_extract_classifies_multi_blog_page_as_collection(monkeypatch):
    stub_document_llm(monkeypatch, "collection", title="Blog")
    html = """
    <html><head><title>Blog · Example Author</title></head><body><main>
    <h1>Blog</h1>
    <section><h2>Personal blog</h2><a href="/fast">Fast</a><p>Notes about speed and institutions.</p></section>
    <section><h2>Company blog</h2><a href="/culture">Culture</a><p>Notes about organizational culture.</p></section>
    </main></body></html>
    """

    page = extract_page(html, "https://patrickcollison.com/blog")

    assert page.document_type == "collection"


def test_extract_classifies_books_page_as_collection(monkeypatch):
    stub_document_llm(monkeypatch, "collection", title="Books", topics=["books", "reading"])
    html = """
    <html><head><title>Books</title></head><body><main>
    <h1>Books</h1>
    <ul><li>Thinking Fast and Slow</li><li>The Dark Forest</li><li>Being Mortal</li></ul>
    <p>2025 books read and recommendations.</p>
    </main></body></html>
    """

    page = extract_page(html, "https://youngkim.co/books")

    assert page.document_type == "collection"


def test_extract_classifies_root_homepage_as_profile(monkeypatch):
    stub_document_llm(monkeypatch, "profile", title="Home", topics=["profile"])
    html = """
    <html><head><title>Home</title></head><body><main>
    <h1>Hey, I'm Young</h1>
    <p>I'm currently a co-founder. Previously I was a CTO. Outside of work, I love reading.</p>
    </main></body></html>
    """

    page = extract_page(html, "https://youngkim.co/")

    assert page.document_type == "profile"


def test_extract_classifies_blog_slug_with_prose_as_essay(monkeypatch):
    stub_document_llm(monkeypatch, "essay")
    html = """
    <html><head><title>Developing Stronger Opinions</title></head><body><main>
    <p>I am very reticent to commit to opinions, but that has costs for thinking.</p>
    <p>""" + " ".join(["personal reasoning research taste judgment uncertainty evidence practice"] * 140) + """</p>
    <p><a href="/blog">Blog</a> <a href="/projects">Projects</a> <a href="/notes">Notes</a></p>
    </main></body></html>
    """

    page = extract_page(html, "https://noahrousell.com/blog/developing-stronger-opinions")

    assert page.document_type == "essay"


def test_extract_classifies_about_page_as_profile(monkeypatch):
    stub_document_llm(monkeypatch, "profile")
    html = """
    <html><head><title>About Jane</title></head><body><main>
    <p>Jane writes software and studies organizations.</p>
    <p>""" + " ".join(["background research projects contact speaking"] * 60) + """</p>
    </main></body></html>
    """
    page = extract_page(html, "https://a.test/about")
    assert page.document_type == "profile"


def test_extract_classifies_docs_page_as_reference(monkeypatch):
    stub_document_llm(monkeypatch, "reference")
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
    stub_document_llm(monkeypatch, "collection")
    html = """
    <html><head><title>Selected Notes</title></head><body><main>
    <p>""" + " ".join(["A short editorial note about a group of readings and collected arguments."] * 50) + """</p>
    </main></body></html>
    """

    page = extract_page(html, "https://example.com/selected-notes")

    assert page.document_type == "collection"


def test_document_analysis_parser_accepts_structured_output():
    parsed = document_classifier._parse_document_analysis_response(
        '{"title":"Blog","summary":"A list of writing.","one_liner":"Archives look passive, but they are maps of taste.","audience":"Readers browsing an archive.","takeaways":["Read the archive","Follow the links"],"topics":["writing","archive"],"category_slug":"writing","document_type":"collection"}'
    )

    assert parsed["title"] == "Blog"
    assert parsed["category_slug"] == "writing"
    assert parsed["document_type"] == "collection"


def test_document_analysis_summary_composes_takeaway_bullets():
    assert document_classifier._normalize_summary(
        "A guide for candidates interviewing for Staff-plus roles.",
        fallback="fallback",
    ) == "A guide for candidates interviewing for Staff-plus roles."
    assert document_classifier._normalize_audience(" Candidates interviewing for Staff-plus roles. ") == (
        "Candidates interviewing for Staff-plus roles."
    )
    assert document_classifier._normalize_one_liner(" X looks like Y, but really Z. ") == "X looks like Y, but really Z."
    assert document_classifier._normalize_takeaways(
        ["Clarify the interview format", "- Prepare leadership examples", "Negotiate details", "Extra item"]
    ) == ["Clarify the interview format", "Prepare leadership examples", "Negotiate details"]


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
