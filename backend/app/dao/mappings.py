import db
from models.models import LinkMapping
from schemas.crawl import LinkMappingCreateParams


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
