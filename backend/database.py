"""
database.py — SQLAlchemy engine and session setup.

Automatically detects whether the DATABASE_URL points to PostgreSQL or SQLite
and configures the engine accordingly.

SSL is enabled for PostgreSQL connections (required by Supabase and most
cloud-hosted PostgreSQL providers). It is skipped for SQLite (local dev).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

DATABASE_URL = settings.DATABASE_URL

# ── Engine configuration ───────────────────────────────────────────────────────

if DATABASE_URL.startswith("sqlite"):
    # SQLite: local development only, no SSL, needs check_same_thread=False
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

else:
    # PostgreSQL (Supabase, Koyeb, or any cloud-hosted PG)
    # Supabase requires SSL. connect_args passes SSL mode to psycopg2.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "require"},
        pool_pre_ping=True,       # Detect and recycle stale connections
        pool_size=5,              # Keep a small pool — cloud DBs have connection limits
        max_overflow=10,
    )

# ── Session factory ────────────────────────────────────────────────────────────

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()