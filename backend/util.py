import time
from urllib.parse import urlparse

def timing_decorator(func):
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        print(f"Function {func.__name__} took {end_time - start_time:.4f} seconds")
        return result

    return wrapper


""" Filter out all static resources and ID links while webscraping """
def is_id_or_static_resource(url: str) -> bool:
    return "#" in url or url.endswith(("png", "jpeg", "jpg", "pdf", "xml", "ipynb", "py"))


def add_https_if_missing(url: str):
    return "https://" + url if not url.startswith(("http://", "https://")) else url


def get_domain(url: str):
    netloc = urlparse(add_https_if_missing(url)).netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # print(get_domain("www.benkuhn.net")) => benkuhn.net
    # print(get_domain("https://benkuhn.net")) => benkuhn.net
    # print(get_domain("https://www.benkuhn.net")) => benkuhn.net
    # print(get_domain("https://engineering.ramp.com/")) => engineering.ramp.com
        
    return netloc
    