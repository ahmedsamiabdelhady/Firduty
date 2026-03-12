"""
database.py — SQLAlchemy engine, session factory, and Base declarative class.

Supabase (PostgreSQL) requires SSL — configured via connect_args.
SQLite is used for local development only (no SSL needed).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./firduty.db")

# PostgreSQL (Supabase) — enforce SSL
# SQLite — no SSL, no extra args needed
_is_postgres = DATABASE_URL.startswith("postgresql")

_engine_kwargs: dict = {}
if _is_postgres:
    _engine_kwargs["connect_args"] = {"sslmode": "require"}
    _engine_kwargs["pool_pre_ping"] = True   # detect stale connections
    _engine_kwargs["pool_recycle"] = 1800    # recycle connections every 30 min


engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session and closes it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()