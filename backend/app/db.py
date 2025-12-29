import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

from app.models.mixins import Base
import app.models.models

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT")
DEV_DATABASE_URL = os.getenv("DEV_DATABASE_URL")
PROD_DATABASE_URL = os.getenv("PROD_DATABASE_URL")

if not DEV_DATABASE_URL:
    raise ValueError("DEV_DATABASE_URL environment variable is required")
if not PROD_DATABASE_URL:
    raise ValueError("PROD_DATABASE_URL environment variable is required")

DATABASE_URL = PROD_DATABASE_URL if ENVIRONMENT == "production" else DEV_DATABASE_URL

# Create sync engine
engine = create_engine(DATABASE_URL, echo=False)

# Create pgvector extension and tables
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()
Base.metadata.create_all(engine)

# Create session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Create scoped session for thread-local session management
session = scoped_session(SessionLocal)
