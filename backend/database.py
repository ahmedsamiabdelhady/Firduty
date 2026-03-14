"""
database.py — SQLAlchemy engine, session factory, and Base declarative class.

Supabase (PostgreSQL) requires SSL — configured via connect_args.
SQLite is used for local development only (no SSL needed).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

DATABASE_URL: str = settings.DATABASE_URL

_is_postgres = DATABASE_URL.startswith("postgresql")

_engine_kwargs: dict = {}
if _is_postgres:
    _engine_kwargs["connect_args"] = {"sslmode": "require"}
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 1800

engine = create_engine(
    DATABASE_URL,
    future=True,
    **_engine_kwargs
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()