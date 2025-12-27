PAGE_TIMEOUT_MS = 5000
BATCH_SIZE = 50
MAX_INTERNAL_LINKS_Q_SIZE = 2000
MAX_CRAWL_ITER_PATIENCE = 10
URL_DEPTH_TOLERANCE = 10
URL_REPETITION_TOLERANCE = 3

NOT_A_BLOG_OR_PERSON_REASON = "Excluded b/c website was not a blog run by an individual"
TIMEOUT_ERROR_REASON = (
    "Excluded b/c website could not be scraped due to too many timeouts"
)
OTHER_ERROR_REASON = "Excluded b/c website could not be scraped due to an error"
MANUALLY_EXCLUDED_REASON = "Excluded manually via the CLI"
TOO_MANY_INTERNAL_LINKS_REASON = "Excluded b/c too many internal links to process."
