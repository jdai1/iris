from __future__ import annotations

import pytest

from iris.services.common.config import MissingOpenAIKeyError
from iris.services.ingestion import source_classifier
from iris.services.ingestion.source_classifier import (
    classify_source_homepage,
    classify_source_url,
)


def test_classifier_ignores_reference_and_video_platforms():
    youtube = classify_source_url("https://www.youtube.com/watch?v=abc")
    wikipedia = classify_source_url("https://en.wikipedia.org/wiki/Foo")
    arxiv = classify_source_url("https://arxiv.org/abs/1234.5678")
    google_books = classify_source_url("https://books.google.com/books?id=abc")
    repec = classify_source_url("https://ideas.repec.org/p/foo/bar.html")

    assert youtube.status == "ignored"
    assert "video platform" in youtube.reason
    assert wikipedia.status == "ignored"
    assert "reference" in wikipedia.reason
    assert arxiv.status == "ignored"
    assert "reference" in arxiv.reason
    assert google_books.status == "ignored"
    assert "reference" in google_books.reason
    assert repec.status == "ignored"
    assert "reference" in repec.reason


def test_classifier_ignores_broad_publication_and_media_domains():
    slate = classify_source_url("https://slate.com/")
    economist = classify_source_url("https://www.economist.com/")
    flickr = classify_source_url("https://flickr.com/photos/example")

    assert slate.status == "ignored"
    assert "publication" in slate.reason
    assert economist.status == "ignored"
    assert "publication" in economist.reason
    assert flickr.status == "ignored"
    assert "media platform" in flickr.reason


def test_classifier_ignores_broad_publishing_platform_roots():
    wordpress = classify_source_url("https://wordpress.com/")
    blogger = classify_source_url("https://blogger.com/")
    wp_me = classify_source_url("https://wp.me/foo")

    assert wordpress.status == "ignored"
    assert "publishing platform" in wordpress.reason
    assert blogger.status == "ignored"
    assert "publishing platform" in blogger.reason
    assert wp_me.status == "ignored"
    assert "publishing platform" in wp_me.reason


def test_classifier_keeps_personal_subdomains_and_unknown_domains_queueable():
    substack = classify_source_url("https://example.substack.com/p/post")
    personal_site = classify_source_url("https://person.github.io/essay")
    unknown = classify_source_url("https://benkuhn.net/essay")

    assert substack.status == "queued"
    assert "personal platform" in substack.reason
    assert personal_site.status == "queued"
    assert "personal platform" in personal_site.reason
    assert unknown.status == "queued"


def test_classifier_rejects_professional_service_homepage_before_llm():
    html = """
    <html>
      <title>Seattle Anxiety Specialists - Psychiatry, Psychology, and Therapy</title>
      <meta name="description" content="A clinical practice offering therapy, psychiatry, treatment, insurance, and patient appointments.">
      <body>
        <h1>Seattle Anxiety Specialists</h1>
        <main>
          Our clinic provides psychiatry, psychology, therapy services, treatment plans,
          insurance support, telehealth, and appointments for patients.
          Schedule a consultation with a clinician.
        </main>
      </body>
    </html>
    """
    result = classify_source_homepage("https://seattleanxiety.com/", html)

    assert result.status == "ignored"
    assert "professional service" in result.reason


def test_classifier_rejects_gambling_spam_homepage_before_llm():
    html = """
    <html>
      <title>Rational Conspiracy - 먹튀사이트 검증 뉴스</title>
      <body>
        <main>
          안전한 온라인 베팅을 위한 먹튀검증 커뮤니티.
          카지노사이트 먹튀 검증과 토토사이트 정보를 제공합니다.
        </main>
      </body>
    </html>
    """
    result = classify_source_homepage("https://rationalconspiracy.com/", html)

    assert result.status == "ignored"
    assert "gambling" in result.reason


def test_classifier_rejects_non_english_homepage_before_platform_shortcut():
    html = """
    <html>
      <title>בלוג אישי</title>
      <body><main>
      זהו טקסט בעברית שמייצג בלוג אישי עם מאמרים ורשומות רבות.
      אנחנו לא רוצים להכניס מקורות שאינם באנגלית לקורפוס בשלב הזה.
      המטרה היא לשמור על חיפוש באנגלית ועל איכות אחידה של מסמכים.
      </main></body>
    </html>
    """
    result = classify_source_homepage("https://example.wordpress.com/", html)

    assert result.status == "ignored"
    assert "non-English" in result.reason


def test_classifier_requires_api_key_for_unclear_homepage(monkeypatch):
    def missing_key(_feature):
        raise MissingOpenAIKeyError("missing test key")

    monkeypatch.setattr(source_classifier, "require_openai_api_key", missing_key)
    html = """
    <html><head><title>Maybe a Blog</title></head><body><main>
    I write about software, organizations, and research taste. These notes are
    written as essays and posts for readers who like longform thinking.
    </main></body></html>
    """

    with pytest.raises(MissingOpenAIKeyError):
        classify_source_homepage("https://maybe-blog.com/", html)


def test_classifier_sends_personal_homepage_with_writing_tab_to_llm(monkeypatch):
    monkeypatch.setattr(source_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        source_classifier,
        "_classify_with_openai",
        lambda _key, _url, _context: {
            "should_crawl": True,
            "reason": "Personal homepage with a writing section.",
        },
    )
    html = """
    <html><head><title>Jason Dai</title></head><body>
      <nav><a href="/">Home</a><a href="/writing">Writing</a><a href="/projects">Projects</a></nav>
      <main>
        <h1>Jason Dai</h1>
        <p>Software engineer. Contact, projects, and professional details.</p>
      </main>
    </body></html>
    """

    result = classify_source_homepage("https://jdai1.github.io/", html)

    assert result.status == "queued"
    assert "writing" in result.reason


def test_classifier_rejects_corporate_blog_homepage_via_llm(monkeypatch):
    monkeypatch.setattr(source_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        source_classifier,
        "_classify_with_openai",
        lambda _key, _url, _context: {
            "should_crawl": False,
            "reason": "Corporate product site with content marketing, not a personal essay archive.",
        },
    )
    html = """
    <html><head><title>Ramp - Finance Automation Platform</title></head><body>
      <nav><a href="/blog">Blog</a><a href="/resources">Resources</a><a href="/customers">Customers</a></nav>
      <main>
        <h1>Spend management and accounting automation</h1>
        <p>Ramp helps companies automate expenses, procurement, bill pay, and finance workflows.</p>
      </main>
    </body></html>
    """

    result = classify_source_homepage("https://ramp.com/", html)

    assert result.status == "ignored"
    assert "Corporate product site" in result.reason


def test_personal_platform_suffix_still_uses_homepage_llm(monkeypatch):
    monkeypatch.setattr(source_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        source_classifier,
        "_classify_with_openai",
        lambda _key, _url, _context: {
            "should_crawl": False,
            "reason": "This is a product site, not an essay archive.",
        },
    )
    html = """
    <html><head><title>Example Substack</title></head><body><main>
    Subscribe to our product updates, feature launches, pricing notes, and customer announcements.
    </main></body></html>
    """

    result = classify_source_homepage("https://example.substack.com/", html)

    assert result.status == "ignored"
    assert "product site" in result.reason


def test_classifier_accepts_personal_substack_newsletter_via_llm(monkeypatch):
    monkeypatch.setattr(source_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        source_classifier,
        "_classify_with_openai",
        lambda _key, _url, _context: {
            "should_crawl": True,
            "reason": "Individual Substack newsletter with authored essays and posts.",
        },
    )
    html = """
    <html><head><title>Goran's Newsletter</title></head><body><main>
      <h1>Goran's Newsletter</h1>
      <p>Essays, notes, and posts by Goran about software, institutions, and culture.</p>
      <article><h2>Recent essay</h2><p>A long personal post.</p></article>
    </main></body></html>
    """

    result = classify_source_homepage("https://goranshbharal.substack.com/", html)

    assert result.status == "queued"
    assert "Substack newsletter" in result.reason


def test_source_classifier_payload_uses_strict_structured_output(monkeypatch):
    captured_payload = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": '{"should_crawl": true, "reason": "Personal essays."}'}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _url, *, headers, json):
            captured_payload.update(json)
            return FakeResponse()

    monkeypatch.setattr(source_classifier.httpx, "Client", FakeClient)

    result = source_classifier._classify_with_openai("test-key", "https://example.com/", "Essays and notes.")

    assert result.should_crawl is True
    assert captured_payload["text"]["format"]["strict"] is True
    assert captured_payload["text"]["format"]["name"] == "source_classification"
    assert captured_payload["max_output_tokens"] == 2000
    assert captured_payload["text"]["format"]["schema"]["properties"]["reason"]["maxLength"] == 240


def test_source_classifier_parser_requires_direct_structured_json():
    with pytest.raises(ValueError):
        source_classifier._parse_classifier_json('Here is JSON: {"should_crawl": true, "reason": "Blog."}')
