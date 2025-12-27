from urllib.parse import urlparse
import re
from collections import Counter


def is_id_or_static_resource(url: str) -> bool:
    parsed = urlparse(add_https_if_missing(url))
    path_lower = parsed.path.lower()
    static_extensions = (".png", ".jpeg", ".jpg", ".pdf", ".xml", ".ipynb", ".py")
    return any(path_lower.endswith(ext) for ext in static_extensions)


def add_https_if_missing(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return "https:" + url
    return "https://" + url


def get_domain(url: str) -> str:
    netloc = urlparse(add_https_if_missing(url)).netloc

    if netloc.startswith("www."):
        netloc = netloc[4:]

    if "@" in netloc:
        netloc = netloc.split("@")[-1]

    return netloc


def get_path(url: str) -> str:
    path = urlparse(add_https_if_missing(url)).path

    path = path.rstrip("/")
    path = re.sub(r"/+", "/", path)
    return path


def get_domain_and_path(url: str) -> str:
    return get_domain(url) + get_path(url)


def sanitize_url(url: str) -> str:
    url = get_domain_and_path(url)
    url = add_https_if_missing(url)
    url = url.rstrip("/")
    return url


def get_url_depth(url: str) -> int:
    return len([p for p in urlparse(url).path.split("/") if p])


def get_url_path_count(url: str) -> Counter:
    return Counter([p for p in urlparse(url).path.split("/") if p])


def is_from_same_domain_or_subdomain(url_a: str, url_b: str) -> bool:
    domain_a = get_domain(url_a)
    domain_b = get_domain(url_b)
    if domain_a == domain_b:
        return True
    return domain_a.endswith("." + domain_b)


def is_external_link(link_url: str, domain_url: str) -> bool:
    link_domain = get_domain(link_url)
    domain = get_domain(domain_url)
    return link_domain != domain
