from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

import os

# Determine the effective database URL.  Test runs set TEST_DATABASE_URL;
# fall back to a generic DATABASE_URL env var, then to the Settings value.
# Ensure the URL uses the psycopg2 driver (postgresql+psycopg2://).
raw_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or settings.database_url
if raw_url.startswith("postgresql://"):
    database_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    database_url = raw_url

if database_url.startswith("sqlite"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(database_url, pool_pre_ping=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
