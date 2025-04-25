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