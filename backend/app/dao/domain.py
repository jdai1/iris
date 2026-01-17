from sqlalchemy import select

import app.db as db
from app.enums.core import DomainStatus
from app.models.models import Domain
from app.schemas.crawl import DomainCreateParams


def create_domain(params: DomainCreateParams) -> Domain:
    """Create a domain in the database."""
    domain = Domain(
        domain_url=params.domain_url,
        entity=params.entity,
        name=params.name,
        status=params.status,
        error_message=params.error_message,
    )
    db.session.add(domain)
    db.session.flush()
    return domain


def create_domains_batch(params_list: list[DomainCreateParams]) -> list[Domain]:
    """Batch create domains in the database."""
    domains = [
        Domain(
            domain_url=params.domain_url,
            entity=params.entity,
            name=params.name,
            status=params.status,
            error_message=params.error_message,
        )
        for params in params_list
    ]
    db.session.add_all(domains)
    db.session.flush()
    return domains


def get_domain_by_url(domain_url: str) -> Domain | None:
    """Get domain by URL."""
    stmt = select(Domain).where(Domain.domain_url == domain_url)
    result = db.session.execute(stmt)
    return result.scalar_one_or_none()


def get_domains_by_urls(domain_urls: list[str]) -> dict[str, Domain]:
    """Get multiple domains by URLs. Returns dict mapping domain_url -> Domain."""
    if not domain_urls:
        return {}

    stmt = select(Domain).where(Domain.domain_url.in_(domain_urls))
    result = db.session.execute(stmt)
    domains = result.scalars().all()
    return {domain.domain_url: domain for domain in domains}


def get_or_create_domain_by_url(domain_url: str) -> Domain:
    """
    Get or create a domain by URL in PENDING state.

    Args:
        domain_url: The domain URL

    Returns:
        Domain object (always in PENDING state if newly created)
    """
    domain = get_domain_by_url(domain_url)

    if domain is not None:
        return domain

    params = DomainCreateParams(
        domain_url=domain_url,
        entity=None,
        name=None,
        status=DomainStatus.PENDING,
        error_message=None,
    )
    return create_domain(params)


def update_domain_status(
    domain: Domain, status: DomainStatus, error_message: str | None = None
) -> None:
    """
    Update domain status and error message.

    Uses flush() to persist changes within a transaction.
    Call db.session.commit() separately if you need to commit the transaction.
    """
    domain.status = status
    if error_message is not None:
        domain.error_message = error_message
    db.session.flush()
