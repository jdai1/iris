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

    # handle @ signs e.g. mailto:
    if "@" in netloc:
        netloc = netloc.split("@")[-1]
        
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

# Return True if url_a is from the same domain or a subdomain of url_b
def is_from_same_domain_or_subdomain(url_a: str, url_b: str) -> bool:
    return get_domain(url_b) in get_domain(url_a)


# ** PASSING
def test_is_from_same_domain_or_subdomain():
    assert(is_from_same_domain_or_subdomain("https://bigdanzblog.wordpress.com/", "https://wordpress.com/"))
    assert(not is_from_same_domain_or_subdomain("https://wordpress.com/", "https://bigdanzblog.wordpress.com/"))
    assert(is_from_same_domain_or_subdomain("scraps.benkuhn.net", "https://www.benkuhn.net/"))