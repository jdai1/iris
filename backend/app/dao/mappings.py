import app.db as db
from app.models.models import DomainMapping, LinkMapping
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
