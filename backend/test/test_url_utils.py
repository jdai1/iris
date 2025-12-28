from app.utils.url_utils import get_domain


class TestGetDomain:
    """Tests for get_domain function."""

    def test_basic_urls_with_protocol(self):
        """Test basic URLs with http/https protocol."""
        assert get_domain("https://example.com") == "example.com"
        assert get_domain("http://example.com") == "example.com"
        assert get_domain("https://example.com/") == "example.com"
        assert get_domain("http://example.com/path") == "example.com"

    def test_urls_without_protocol(self):
        """Test URLs without protocol (should add https://)."""
        assert get_domain("example.com") == "example.com"
        assert get_domain("example.com/path") == "example.com"

    def test_urls_with_www_prefix(self):
        """Test that www. prefix is removed."""
        assert get_domain("https://www.example.com") == "example.com"
        assert get_domain("www.example.com") == "example.com"
        assert get_domain("http://www.example.com/path") == "example.com"

    def test_subdomains_preserved(self):
        """Test that subdomains are preserved (except www)."""
        assert get_domain("https://blog.example.com") == "blog.example.com"
        assert get_domain("https://sub.example.com") == "sub.example.com"
        assert get_domain("https://api.example.com") == "api.example.com"
        assert (
            get_domain("https://www.blog.example.com") == "blog.example.com"
        )  # www removed
        assert get_domain("https://sub.blog.example.com") == "sub.blog.example.com"

    def test_multiple_subdomains(self):
        """Test URLs with multiple subdomains."""
        assert get_domain("https://a.b.c.example.com") == "a.b.c.example.com"
        assert get_domain("https://www.a.b.c.example.com") == "a.b.c.example.com"

    def test_email_style_urls(self):
        """Test email-style URLs (user@domain.com)."""
        assert get_domain("user@example.com") == "example.com"
        assert get_domain("https://user@example.com") == "example.com"
        assert get_domain("user@blog.example.com") == "blog.example.com"

    def test_urls_with_ports(self):
        """Test URLs with port numbers."""
        assert get_domain("https://example.com:443") == "example.com:443"
        assert get_domain("https://example.com:8080") == "example.com:8080"
        assert get_domain("https://blog.example.com:443") == "blog.example.com:443"
        assert (
            get_domain("https://www.example.com:443") == "example.com:443"
        )  # www removed

    def test_urls_with_paths_query_fragments(self):
        """Test that paths, query strings, and fragments are ignored."""
        assert get_domain("https://example.com/path/to/page") == "example.com"
        assert get_domain("https://example.com?query=value") == "example.com"
        assert get_domain("https://example.com#fragment") == "example.com"
        assert (
            get_domain("https://example.com/path?query=value#fragment") == "example.com"
        )
        assert get_domain("https://blog.example.com/path/to/page") == "blog.example.com"

    def test_protocol_relative_urls(self):
        """Test protocol-relative URLs (//example.com)."""
        assert get_domain("//example.com") == "example.com"
        assert get_domain("//www.example.com") == "example.com"
        assert get_domain("//blog.example.com") == "blog.example.com"

    def test_localhost(self):
        """Test localhost URLs."""
        assert get_domain("http://localhost") == "localhost"
        assert get_domain("http://localhost:8000") == "localhost:8000"
        assert get_domain("http://www.localhost") == "localhost"  # www removed

    def test_ip_addresses(self):
        """Test IP addresses."""
        assert get_domain("http://192.168.1.1") == "192.168.1.1"
        assert get_domain("http://192.168.1.1:8080") == "192.168.1.1:8080"
        assert get_domain("https://127.0.0.1") == "127.0.0.1"

    def test_edge_cases(self):
        """Test edge cases."""
        # Just domain name
        assert get_domain("example.com") == "example.com"

        # Domain with trailing slash
        assert get_domain("example.com/") == "example.com"

        # Domain with multiple slashes
        assert get_domain("https://example.com//path") == "example.com"

        # Subdomain that looks like www but isn't
        assert (
            get_domain("https://wwwww.example.com") == "wwwww.example.com"
        )  # Not www.
        assert get_domain("https://wwwx.example.com") == "wwwx.example.com"  # Not www.

    def test_complex_real_world_examples(self):
        """Test complex real-world URL examples."""
        # GitHub pages
        assert get_domain("https://jdai1.github.io") == "jdai1.github.io"
        assert get_domain("https://www.jdai1.github.io") == "jdai1.github.io"

        # Medium
        assert get_domain("https://medium.com/@username") == "medium.com"

        # Substack
        assert get_domain("https://subdomain.substack.com") == "subdomain.substack.com"

        # Custom domains with subdomains
        assert get_domain("https://blog.example.co.uk") == "blog.example.co.uk"
        assert get_domain("https://www.blog.example.co.uk") == "blog.example.co.uk"
