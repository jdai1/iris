from db import EntryDriver, DomainDriver, SkippedDomainDriver
from url_utils import get_domain

entry_driver = EntryDriver()
domain_driver = DomainDriver()
skipped_domain_driver = SkippedDomainDriver()

def inspect_domain(domain_url: str):
    domain = domain_driver.get_domain(domain_url)
    print(domain.domain_url)
    print(domain.entity)
    print(domain.external_domains)
    print(domain.external_links)
    print(domain.parsed_internal_links)
    print(domain.skipped_internal_links)
    print(domain.date_last_scraped)

    for l in domain.external_links:
        assert get_domain(l) in domain.external_domains

    
def inspect_entries_of_domain(domain_url: str):
    entries = entry_driver.get_entries_for_domain(domain_url)
    data = [(e.title, e.entry_url, e.domain_url, e.title, e.author) for e in entries]
    col_widths = [max(len(row[i]) for row in data) for i in range(len(data[0]))]

    # Print each row with padded columns
    for row in data:
        print("  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))


def inspect_entries_that_link_to_this_url(url: str):
    entries = entry_driver.get_entries_that_link_to_url(url)
    if not entries:
        return
    
    for e in entries:
        print(e.title, e.entry_url)


if __name__ == "__main__":
    # inspect_domain("bigdanzblog.wordpress.com")
    # inspect_entries_that_link_to_this_url("https://akka.io")
    # inspect_entries_of_domain("bigdanzblog.wordpress.com")
    # entry_driver.clear()
    ents = entry_driver.get_all_entries()
    # ents = entry_driver.search("eye tracking")
    for e in ents:
        print(e.entry_url)