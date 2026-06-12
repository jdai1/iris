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


def test_personal_platform_suffix_still_uses_homepage_llm(monkeypatch):
    monkeypatch.setattr(source_classifier, "require_openai_api_key", lambda _feature: "test-key")
    monkeypatch.setattr(
        source_classifier,
        "_classify_with_openai",
        lambda _key, _url, _context: {
            "should_crawl": False,
            "confidence": 0.88,
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
