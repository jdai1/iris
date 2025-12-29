import uuid
from datetime import date

import factory

from app.enums.core import DomainStatus
from app.models.models import (
    Domain,
    DomainMapping,
    Entry,
    Link,
    LinkMapping,
)


class DomainFactory(factory.alchemy.SQLAlchemyModelFactory):
    """Factory for Domain model."""

    class Meta:
        model = Domain
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid.uuid4)
    domain_url = factory.Faker("domain_name")
    entity = factory.Iterator(["person", "organization", "unknown"])
    name = factory.Faker("name")
    status = DomainStatus.PENDING
    error_message = None


class LinkFactory(factory.alchemy.SQLAlchemyModelFactory):
    """Factory for Link model."""

    class Meta:
        model = Link
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid.uuid4)
    url = factory.Faker("url")
    domain = factory.SubFactory(DomainFactory)


class EntryFactory(factory.alchemy.SQLAlchemyModelFactory):
    """Factory for Entry model."""

    class Meta:
        model = Entry
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid.uuid4)
    link = factory.SubFactory(LinkFactory)
    title = factory.Faker("sentence", nb_words=6)
    summary = factory.Faker("text", max_nb_chars=200)
    topics = factory.LazyFunction(lambda: ["technology", "programming"])
    author = factory.Faker("name")
    date_published = factory.LazyFunction(lambda: date.today())
    embedding = factory.LazyFunction(lambda: [0.0] * 1536)  # Dummy embedding vector


class LinkMappingFactory(factory.alchemy.SQLAlchemyModelFactory):
    """Factory for LinkMapping model."""

    class Meta:
        model = LinkMapping
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid.uuid4)
    source_link = factory.SubFactory(LinkFactory)
    target_link = factory.SubFactory(LinkFactory)


class DomainMappingFactory(factory.alchemy.SQLAlchemyModelFactory):
    """Factory for DomainMapping model."""

    class Meta:
        model = DomainMapping
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid.uuid4)
    source_domain = factory.SubFactory(DomainFactory)
    target_domain = factory.SubFactory(DomainFactory)
