from db import EntryDriver, DomainDriver, ExcludedDomainDriver
from url_utils import get_domain
import sys

entry_driver = EntryDriver()
domain_driver = DomainDriver()
skipped_domain_driver = ExcludedDomainDriver()

def inspect_domain(domain_url: str):
    domain = domain_driver.get_domain(domain_url)
    print(domain.domain_url)
    print(domain.entity)
    print("======= target internal links =======")
    print("\n".join(sorted(domain.target_internal_links)))
    print("======= nontarget internal links =======")
    print("\n".join(sorted(domain.nontarget_internal_links)))
    print(domain.date_last_scraped)

    for l in domain.external_links:
        assert get_domain(l) in domain.external_domains

    
def inspect_entries_of_domain(domain_url: str):
    MAX_DISPLAY_LEN = 60
    entries = entry_driver.get_entries_for_domain(domain_url)
    data = [(e.title, e.entry_url, e.author) for e in entries]
    
    col_widths = [
        min(MAX_DISPLAY_LEN, max(len(row[i]) for row in data))
        for i in range(len(data[0]))
    ]
    
    for row in data:
        print("  ".join(
            (cell[:MAX_DISPLAY_LEN]).ljust(col_widths[i])
            for i, cell in enumerate(row)
        ))



def inspect_entries_that_link_to_this_url(url: str):
    entries = entry_driver.get_entries_that_link_to_url(url)
    if not entries:
        return
    
    for e in entries:
        print(e.title, e.entry_url)


def inspect_domain_and_entries():
    domain_url = sys.argv[1]
    
    inspect_domain(domain_url)
    inspect_entries_of_domain(domain_url)

if __name__ == "__main__":
    inspect_domain_and_entries()