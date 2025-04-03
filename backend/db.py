from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from model import Entry

Base = declarative_base()


class DBEntry(Base):
    __tablename__ = "Entries"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    topics = Column(String, nullable=False)
    author = Column(String, nullable=False)
    date = Column(String, nullable=False)
    url = Column(String, nullable=False)
    link_id = Column(Integer, ForeignKey("Links.url"), nullable=True)
    link = relationship("Link", back_populates="entries")

    def __repr__(self):
        return f"<Entry(blog='{self.blog}', name={self.name}, date='{self.date}', topics='{self.topics}' author='{self.author}' url='{self.url}' summary='{self.summary}' >"


class Link(Base):
    __tablename__ = "Links"
    url = Column(String, primary_key=True)
    entity = Column(String, nullable=False)
    name = Column(String, nullable=False)
    blog = Column(Boolean, nullable=False)
    parsed_blogs = Column(Boolean, nullable=False)
    parsed_links = Column(Boolean, nullable=False)
    external_domains = Column(String, nullable=True)
    external_links = Column(String, nullable=True)

    entries = relationship("DBEntry", back_populates="link")

    def __repr__(self):
        return f"<Entry(url='{self.url}', external_domains='{self.external_domains}', external_links='{self.external_links}'>"


engine = create_engine("sqlite:///store.db", echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def add_entries(
    entries: list[Entry],
):
    db_entries = [DBEntry(**entry.__dict__) for entry in entries]
    session = Session()
    session.add_all(db_entries)
    session.commit()
    session.close()


def query_entries():
    session = Session()
    for entry in session.query(DBEntry).all():
        print(entry)
    session.close()


def add_link(
    url: str,
    entity: str,
    name: str,
    blog: bool,
    external_domains: Optional[list[str]] = None,
    external_links: Optional[list[str]] = None,
):
    link = Link(
        url=url,
        entity=entity,
        name=name,
        blog=blog,
        parsed_blogs=False,
        parsed_links=False,
        external_domains=",".join(external_domains) if external_domains else None,
        external_links=",".join(external_links) if external_links else None,
    )

    session = Session()
    session.add(link)
    session.commit()
    session.close()


def query_links():
    session = Session()
    links = session.query(Link).all()
    session.close()
    return links
