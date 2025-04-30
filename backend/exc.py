
# While calling crawl_domain in ingest, one of the following errors happened:
# 1) Despite retries w/ exponentially decreasing batch sizes, the number of timeouts was still too high
# 2) Some other problem happened while scraping
class FatalException(Exception):
    pass

# Skipped calling crawl_domain in ingest b/c 
# 1) It's already in the SkippedDomain table
# 2) It's already been scraped in the last timedelta
# 3) The website is not a blog run by an individual as determined by classify_domain()
# 4) Manually skipped via CLI 
class SkipCrawlingDomainException(Exception): 
    pass

# During crawl_domain, this error is thrown when the number of timeouts becomes proportionally too high
class TooManyCrawlingTimeoutsException(Exception):
    pass


# During crawl_domain, this error is thrown if the total number of internal_links to traverse becomes too high
class TooManyInternalLinks(Exception):
    pass