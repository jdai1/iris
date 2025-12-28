from sqlalchemy import select

import app.db as db
from app.models.models import Link
from app.schemas.crawl import LinkCreateParams


def create_link(params: LinkCreateParams) -> Link:
    """Create a link in the database."""
    link = Link(
        url=params.url,
        domain_id=params.domain_id,
    )
    db.session.add(link)
    db.session.flush()
    return link


def create_links_batch(params_list: list[LinkCreateParams]) -> list[Link]:
    """Batch create links in the database."""
    links = [
        Link(
            url=params.url,
            domain_id=params.domain_id,
        )
        for params in params_list
    ]
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
