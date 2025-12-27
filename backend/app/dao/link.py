from sqlalchemy import select

import db
from models.models import Link


def create_link(link: Link) -> Link:
    """Create a link in the database."""
    db.session.add(link)
    db.session.flush()
    return link


def create_links_batch(links: list[Link]) -> list[Link]:
    """Batch create links in the database."""
    db.session.add_all(links)
    db.session.flush()
    return links


def get_link_by_url(url: str) -> Link | None:
    """Get link by URL."""
    stmt = select(Link).where(Link.url == url)
    result = db.session.execute(stmt)
    return result.scalar_one_or_none()


def get_links_by_urls(urls: list[str]) -> dict[str, Link]:
    """Get multiple links by URLs. Returns dict mapping url -> Link."""
    if not urls:
        return {}

    stmt = select(Link).where(Link.url.in_(urls))
    result = db.session.execute(stmt)
    links = result.scalars().all()
    return {link.url: link for link in links}
