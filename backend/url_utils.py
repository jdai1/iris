from urllib.parse import urlparse
import re

""" Filter out all static resources and ID URLs while webscraping """
def is_id_or_static_resource(url: str) -> bool:
    return "#" in url or url.endswith(("png", "jpeg", "jpg", "pdf", "xml", "ipynb", "py"))


def add_https_if_missing(url: str):
    return "https://" + url if not url.startswith(("http://", "https://")) else url


def get_domain(url: str):
    # netloc => everything between scheme e.g. http/https and path
    netloc = urlparse(add_https_if_missing(url)).netloc

    # remove www.
    if netloc.startswith("www."):
        netloc = netloc[4:] 
        
    return netloc

def get_path(url: str):
    # path => everything between the domain and the params/query
    path = urlparse(add_https_if_missing(url)).path

    # remove redundant slashes
    path = path.rstrip("/")                       
    path = re.sub(r'/+', '/', path)
    return path

def get_domain_and_path(url: str):
    return get_domain(url) + get_path(url)


def sanitize_url(url: str):
    url = get_domain_and_path(url)
    url = add_https_if_missing(url)
    url = url.rstrip("/")
    return url

# NOTE: Crawl4ai defines an interal link to be any link that shares the same domain or has a parent domain
# encompassing the subdomain. e.g. if it crawled jdai1.github.io and found github.io, it would
# consider that an internal link 
# 
# We want to define a more strict definition based on netloc

def is_from_same_domain(url_a: str, url_b: str) -> bool:
    return get_domain(url_a) == get_domain(url_b)


def is_valid_internal_link(entry_url: str, href: str) -> bool:
    return not is_id_or_static_resource(href) and is_from_same_domain(entry_url, href)