from typing import List, Optional
from datetime import date
from sqlalchemy import create_engine, ForeignKey, String, func
from sqlalchemy.sql.expression import cast
from sqlalchemy.orm import (
    sessionmaker,
    relationship,
    declarative_base,
    Mapped,
    mapped_column,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql.ext import to_tsvector, phraseto_tsquery

Base = declarative_base()
engine = create_engine(
    "postgresql+psycopg2://postgres:1234@localhost:5432/postgres", echo=False
)
SessionMaker = sessionmaker(bind=engine)


class SkippedDomain(Base):
    __tablename__ = "SkippedDomains"
    domain_url: Mapped[str] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(nullable=False)

    def __repr__(self):
        return f"<SkippedDomain(url='{self.domain_url}', entity='{self.entity}' reason='{self.reason}'>"


class Domain(Base):
    __tablename__ = "Domains"
    domain_url: Mapped[str] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    external_domains: Mapped[List[str]] = mapped_column(
        type_=ARRAY(String), nullable=False
    )
    parsed_internal_links: Mapped[List[str]] = mapped_column(
        type_=ARRAY(String), nullable=False
    )
    skipped_internal_links: Mapped[List[str]] = mapped_column(
        type_=ARRAY(String), nullable=False
    )
    external_links: Mapped[List[str]] = mapped_column(
        type_=ARRAY(String), nullable=False
    )
    date_last_scraped: Mapped[date] = mapped_column(nullable=True)

    entries: Mapped[List["Entry"]] = relationship("Entry", back_populates="domain")

    def __repr__(self):
        return f"<Domain(url='{self.domain_url}', entity='{self.entity}', name='{self.name}' ...>"


class Entry(Base):
    __tablename__ = "Entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    summary: Mapped[str] = mapped_column(nullable=False)
    topics: Mapped[List[str]] = mapped_column(type_=ARRAY(String), nullable=False)
    author: Mapped[str] = mapped_column(nullable=False)
    date_published: Mapped[date] = mapped_column(nullable=True)
    links: Mapped[List[str]] = mapped_column(type_=ARRAY(String), nullable=False)
    entry_url: Mapped[str] = mapped_column(nullable=False)
    domain_url: Mapped[str] = mapped_column(ForeignKey("Domains.domain_url"))
    domain: Mapped[Domain] = relationship("Domain", back_populates="entries")

    def __repr__(self):
        return f"<Entry(title={self.title}, date='{self.date_published}', topics='{self.topics}', author='{self.author}', url='{self.entry_url}', summary='{self.summary}', domain_url='{self.domain_url}'>"


# This line needs to go after the definition of the above classes — the definition of the classes adds their data to the metadata.
Base.metadata.create_all(engine)


class EntryDriver:
    def add_entries(self, entries: list[Entry]):
        session = SessionMaker()
        session.add_all(entries)
        session.commit()
        session.close()

    def get_all_entries(self):
        session = SessionMaker()
        entries = session.query(Entry).all()
        session.close()
        return entries

    def get_entries_for_domain(self, domain_url: str):
        session = SessionMaker()
        entries = session.query(Entry).filter(Entry.domain_url == domain_url).all()
        session.close()
        return entries

    def search(self, query: str) -> list[Entry]:
        session = SessionMaker()
        tsvec = to_tsvector(
            "english",
            Entry.title
            + " "
            + Entry.summary
            + " "
            + cast(Entry.topics, String)
            + " "
            + Entry.author,
        )
        print(tsvec)
        return (
            session.query(Entry)
            .filter(tsvec.op("@@")(phraseto_tsquery("english", query)))
            .all()
        )

    def get_entries_that_link_to_url(self, url: str) -> Optional[list[Entry]]:
        session = SessionMaker()
        entries = session.query(Entry).filter(Entry.links.contains([url])).all()
        session.close()
        return entries

    def clear(self):
        session = SessionMaker()
        session.query(Entry).delete()
        session.commit()
        session.close()


class DomainDriver:
    def contains_domain(self, domain_url: str) -> bool:
        session = SessionMaker()
        exists = session.query(Domain).get(domain_url) is not None
        session.close()
        return exists
    
    def add_domain(self, domain: Domain):
        session = SessionMaker()
        try:
            session.add(domain)
            session.commit()
            session.close()
        except IntegrityError:
            raise Exception(f"DomainDriver: {domain.domain_url} already exists")

    def get_all_domains(self) -> List[Domain]:
        session = SessionMaker()
        domains = session.query(Domain).all()
        session.close()
        return domains

    def get_domain(self, domain_url: str) -> Domain:
        session = SessionMaker()
        domain = session.query(Domain).filter(Domain.domain_url == domain_url).all()[0]
        session.close()
        return domain

    def update_external_links_and_domains(
        self,
        domain_url: str,
        external_domains: List[str],
        external_links: List[str],
        parsed_internal_links: List[str],
        skipped_internal_links: List[str],
        date_last_scraped: date
    ):
        session = SessionMaker()
        print(domain_url)
        domain = session.query(Domain).filter(Domain.domain_url == domain_url).first()

        if not domain:
            raise Exception(f"DomainDriver: {domain_url} does not exist")
        update_values = {}
        update_values["external_domains"] = external_domains
        update_values["external_links"] = external_links
        update_values["parsed_internal_links"] = parsed_internal_links
        update_values["skipped_internal_links"] = skipped_internal_links
        update_values["date_last_scraped"] = date_last_scraped

        # Update the link
        session.query(Domain).filter(Domain.domain_url == domain_url).update(
            update_values
        )
        session.commit()
        session.close()

    def clear(self):
        session = SessionMaker()
        session.query(Domain).delete()
        session.commit()
        session.close()


class SkippedDomainDriver:
    def contains_skipped_domain(self, domain_url: str) -> bool:
        session = SessionMaker()
        exists = session.query(SkippedDomain).get(domain_url) is not None
        session.close()
        return exists
    
    def add_skipped_domain(self, domain: SkippedDomain):
        session = SessionMaker()
        try:
            session.add(domain)
            session.commit()
            session.close()
        except IntegrityError:
            raise Exception(f"DomainDriver: {domain.domain_url} already exists")

    def get_all_skipped_domains(self) -> List[SkippedDomain]:
        session = SessionMaker()
        skipped_domains = session.query(SkippedDomain).all()
        session.close()
        return skipped_domains

    def clear(self):
        session = SessionMaker()
        session.query(SkippedDomain).delete()
        session.commit()
        session.close()

def drop_tables_and_recreate():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
