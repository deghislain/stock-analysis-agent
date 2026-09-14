"""
Database engine, session factory, and table-creation helper for the Portfolio
module (Sub-Task P1).

Three public names are exported:

    engine        — the SQLAlchemy ``Engine`` instance configured from
                    ``settings.database_url``.
    SessionLocal  — a ``sessionmaker`` factory; call ``SessionLocal()`` to
                    obtain a new ``Session``.  Prefer the ``get_db()``
                    FastAPI dependency (``app/api/dependencies.py``) over
                    instantiating sessions directly in route handlers.
    init_db()     — creates all tables that do not yet exist.  Safe to call
                    multiple times (``checkfirst=True`` is the default for
                    ``create_all``).  Called once from the app ``lifespan``
                    startup block in ``app/main.py``.

Design notes
────────────
- ``check_same_thread=False`` is passed via ``connect_args`` for SQLite only.
  FastAPI/uvicorn can invoke route handlers from different threads, which would
  otherwise cause SQLite to raise ``ProgrammingError: SQLite objects created in
  a thread can only be used in that same thread``.
- The ``connect_args`` guard is intentionally narrow: it is applied only when
  the URL scheme starts with ``"sqlite"``, so switching to PostgreSQL via a
  ``DATABASE_URL`` env override requires no code changes.
- ``autocommit=False`` and ``autoflush=False`` are the SQLAlchemy 2.x
  recommended defaults for request-scoped sessions; explicit ``db.commit()``
  calls in ``crud.py`` make every transaction boundary visible and auditable.
"""

from __future__ import annotations

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.portfolio.models import Base
from app.logger import get_logger

logger = get_logger(__name__)


# ── Engine ────────────────────────────────────────────────────────────────────

def _build_engine() -> Engine:
    """
    Construct the SQLAlchemy engine from ``settings.database_url``.

    Applies ``check_same_thread=False`` automatically when the URL is a
    SQLite URL, which is required for multi-threaded ASGI frameworks.
    """
    url = settings.database_url
    connect_args: dict = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args)


engine: Engine = _build_engine()
"""
SQLAlchemy ``Engine`` configured from ``settings.database_url``.

Shared across the application lifetime; do not close or recreate it at
runtime.
"""


# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)
"""
Session factory for the portfolio database.

Call ``SessionLocal()`` to obtain a new ``Session``, or — preferably —
use the ``get_db()`` dependency from ``app/api/dependencies.py`` which
handles opening and closing the session for each request automatically.
"""


# ── Table creation ────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create all portfolio tables that do not yet exist in the database.

    Uses ``Base.metadata.create_all`` with the default ``checkfirst=True``
    behaviour, so calling this function multiple times is safe — it will
    never drop or truncate existing tables.

    Called once from the ``lifespan`` startup block in ``app/main.py``.
    """
    logger.info(
        "Initialising portfolio database",
        extra={"database_url": settings.database_url},
    )
    Base.metadata.create_all(bind=engine)
    logger.info("Portfolio database tables ready")
