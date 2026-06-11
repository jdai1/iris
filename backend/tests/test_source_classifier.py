from __future__ import annotations

from iris.source_classifier import classify_source_homepage, classify_source_url


def test_classifier_ignores_reference_and_video_platforms():
    youtube = classify_source_url("https://www.youtube.com/watch?v=abc")
    wikipedia = classify_source_url("https://en.wikipedia.org/wiki/Foo")
    arxiv = classify_source_url("https://arxiv.org/abs/1234.5678")
    google_books = classify_source_url("https://books.google.com/books?id=abc")
    repec = classify_source_url("https://ideas.repec.org/p/foo/bar.html")

    assert youtube.status == "ignored"
    assert youtube.source_type == "video_platform"
    assert wikipedia.status == "ignored"
    assert wikipedia.source_type == "reference"
    assert arxiv.status == "ignored"
    assert arxiv.source_type == "reference"
    assert google_books.status == "ignored"
    assert google_books.source_type == "reference"
    assert repec.status == "ignored"
    assert repec.source_type == "reference"


def test_classifier_ignores_broad_publication_and_media_domains():
    slate = classify_source_url("https://slate.com/")
    economist = classify_source_url("https://www.economist.com/")
    flickr = classify_source_url("https://flickr.com/photos/example")

    assert slate.status == "ignored"
    assert slate.source_type == "publication"
    assert economist.status == "ignored"
    assert economist.source_type == "publication"
    assert flickr.status == "ignored"
    assert flickr.source_type == "media_platform"


def test_classifier_ignores_broad_publishing_platform_roots():
    wordpress = classify_source_url("https://wordpress.com/")
    blogger = classify_source_url("https://blogger.com/")
    wp_me = classify_source_url("https://wp.me/foo")

    assert wordpress.status == "ignored"
    assert wordpress.source_type == "publishing_platform"
    assert blogger.status == "ignored"
    assert blogger.source_type == "publishing_platform"
    assert wp_me.status == "ignored"
    assert wp_me.source_type == "publishing_platform"


def test_classifier_keeps_personal_subdomains_and_unknown_domains_queueable():
    substack = classify_source_url("https://example.substack.com/p/post")
    personal_site = classify_source_url("https://person.github.io/essay")
    unknown = classify_source_url("https://benkuhn.net/essay")

    assert substack.status == "queued"
    assert substack.source_type == "newsletter"
    assert personal_site.status == "queued"
    assert personal_site.source_type == "personal_site"
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
    assert result.source_type == "professional_service"


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
    assert result.source_type == "spam_gambling"


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
    assert result.source_type == "non_english"
