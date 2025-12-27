from sqlalchemy import select

import db
from models.models import Domain


def create_domain(domain: Domain) -> Domain:
    """Create a domain in the database."""
    db.session.add(domain)
    db.session.flush()
    return domain


def get_domain_by_url(domain_url: str) -> Domain | None:
    """Get domain by URL."""
    stmt = select(Domain).where(Domain.domain_url == domain_url)
    result = db.session.execute(stmt)
    return result.scalar_one_or_none()
