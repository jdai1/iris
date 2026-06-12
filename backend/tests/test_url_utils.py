from iris.services.common.url_utils import domain_for_url, normalize_url


def test_normalize_url_strips_tracking_and_www():
    assert (
        normalize_url("HTTPS://www.Example.com/a/?utm_source=x&b=2#frag")
        == "https://example.com/a?b=2"
    )


def test_domain_for_url_adds_scheme():
    assert domain_for_url("www.example.com/path") == "example.com"

