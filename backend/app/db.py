import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models.mixins import Base

# Get database URL from environment or use default
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:1234@localhost:5432/postgres"
)

# Create sync engine
engine = create_engine(DATABASE_URL, echo=False)

# Create session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Create scoped session for thread-local session management
session = scoped_session(SessionLocal)
