from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref"}
MAX_DOMAIN_CHARS = 255
VALID_HOST_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]+)?$")


def ensure_scheme(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return f"https://{url}"


def normalize_url(url: str, base_url: str | None = None) -> str:
    if base_url:
        url = urljoin(base_url, url)
    url = ensure_scheme(url)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_KEYS or any(lowered.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items))
    return urlunparse((scheme, netloc, path, "", query, ""))


def domain_for_url(url: str) -> str:
    parsed = urlparse(ensure_scheme(url))
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or len(host) > MAX_DOMAIN_CHARS:
        return False
    if any(char.isspace() for char in host):
        return False
    if not VALID_HOST_RE.match(host):
        return False
    return "." in host or host.startswith("localhost")


def root_url_for_domain(url: str) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    return urlunparse((parsed.scheme or "https", parsed.netloc, "/", "", "", ""))


def same_domain(a: str, b: str) -> bool:
    return domain_for_url(a) == domain_for_url(b)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_probably_static(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(
        (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".svg",
            ".ico",
            ".css",
            ".js",
            ".pdf",
            ".zip",
            ".gz",
            ".mp4",
            ".mp3",
            ".mov",
        )
    )
