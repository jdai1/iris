import uuid

from sqlalchemy import select

import app.db as db
from app.models.models import DomainMapping, LinkAliasMapping, LinkMapping
from app.schemas.crawl import DomainMappingCreateParams, LinkMappingCreateParams


def create_link_mappings_batch(
    params_list: list[LinkMappingCreateParams],
) -> list[LinkMapping]:
    """Batch create link mappings in the database."""
    mappings = [
        LinkMapping(
            source_link_id=params.source_link_id, target_link_id=params.target_link_id
        )
        for params in params_list
    ]
    db.session.add_all(mappings)
    db.session.flush()
    return mappings


def create_domain_mappings_batch(
    params_list: list[DomainMappingCreateParams],
) -> list[DomainMapping]:
    """Batch create domain mappings in the database."""
    mappings = [
        DomainMapping(
            source_domain_id=params.source_domain_id,
            target_domain_id=params.target_domain_id,
        )
        for params in params_list
    ]
    db.session.add_all(mappings)
    db.session.flush()
    return mappings


def get_existing_link_mappings(
    source_link_ids: set[uuid.UUID], target_link_ids: set[uuid.UUID]
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """
    Get existing link mappings for given source and target link IDs.

    Returns:
        Set of (source_link_id, target_link_id) tuples for existing mappings
    """
    if not source_link_ids or not target_link_ids:
        return set()

    stmt = select(LinkMapping).where(
        LinkMapping.source_link_id.in_(source_link_ids),
        LinkMapping.target_link_id.in_(target_link_ids),
    )
    existing_mappings = db.session.execute(stmt).scalars().all()
    return {
        (mapping.source_link_id, mapping.target_link_id)
        for mapping in existing_mappings
    }


def get_existing_domain_mappings(
    source_domain_id: uuid.UUID, target_domain_ids: set[uuid.UUID]
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """
    Get existing domain mappings for given source domain and target domain IDs.

    Returns:
        Set of (source_domain_id, target_domain_id) tuples for existing mappings
    """
    if not target_domain_ids:
        return set()

    stmt = select(DomainMapping).where(
        DomainMapping.source_domain_id == source_domain_id,
        DomainMapping.target_domain_id.in_(target_domain_ids),
    )
    existing_mappings = db.session.execute(stmt).scalars().all()
    return {
        (mapping.source_domain_id, mapping.target_domain_id)
        for mapping in existing_mappings
    }


def create_link_alias_mapping(
    alias_url: str, canonical_link_id: uuid.UUID
) -> LinkAliasMapping:
    """Create a link alias mapping."""
    mapping = LinkAliasMapping(
        alias_url=alias_url,
        canonical_link_id=canonical_link_id,
    )
    db.session.add(mapping)
    db.session.flush()
    return mapping


def get_existing_link_alias_mappings(alias_urls: set[str]) -> set[str]:
    """
    Get existing link alias mappings for given alias URLs.

    Returns:
        Set of alias URLs that already have mappings
    """
    if not alias_urls:
        return set()

    stmt = select(LinkAliasMapping).where(LinkAliasMapping.alias_url.in_(alias_urls))
    existing_mappings = db.session.execute(stmt).scalars().all()
    return {mapping.alias_url for mapping in existing_mappings}
