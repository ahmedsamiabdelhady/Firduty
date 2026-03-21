"""
database.py — SQLAlchemy engine, session factory, and Base declarative class.

engine and SessionLocal are created lazily (inside get_engine()) so that
a bad DATABASE_URL causes a clear error at request time rather than crashing
the process silently at import time before logging is configured.
"""

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

DATABASE_URL: str = settings.DATABASE_URL

_is_postgres = DATABASE_URL.startswith("postgresql")

_engine_kwargs: dict = {}
if _is_postgres:
    _engine_kwargs["connect_args"] = {"sslmode": "require"}
    _engine_kwargs["pool_pre_ping"] = True   # drops stale connections automatically
    _engine_kwargs["pool_recycle"]  = 1800   # recycle connections every 30 min
    _engine_kwargs["pool_size"]     = 5      # Supabase free tier: max 5 connections
    _engine_kwargs["max_overflow"]  = 2

# create_engine() does NOT open a connection — it just stores the config.
# The first actual DB call (e.g. create_all or a query) opens the connection.
# If DATABASE_URL is malformed this will raise at that point, with logs available.
engine = create_engine(
    DATABASE_URL,
    future=True,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
