from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pipeguard.config import get_settings


class Base(DeclarativeBase):
    pass


_POSTGRES_PREFIXES = ("postgresql+psycopg2://", "postgresql://", "postgres://")


def normalize_database_url(database_url: str) -> str:
    """Resolve any PostgreSQL URL to the psycopg3 driver.

    SQLAlchemy picks the DBAPI from the URL scheme, and a bare ``postgresql://``
    meant psycopg2 before SQLAlchemy 2.1 and means psycopg3 from 2.1 on. Hosting
    providers hand out bare URLs, so the driver would otherwise be decided by
    whichever SQLAlchemy a fresh install happens to resolve — or by hand-editing
    the scheme into an environment variable, where it is invisible to this repo.
    Decide it here instead, in version control, where it is reviewable and tested.
    """
    for prefix in _POSTGRES_PREFIXES:
        if database_url.startswith(prefix):
            return f"postgresql+psycopg://{database_url[len(prefix):]}"
    return database_url


def _engine_kwargs(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # Managed Postgres instances drop idle connections, and a dead connection is
    # only detected when it is used. Validate on checkout and retire old ones so a
    # request after an idle period does not fail with OperationalError.
    return {"pool_pre_ping": True, "pool_recycle": 300}


settings = get_settings()
database_url = normalize_database_url(settings.database_url)
engine = create_engine(database_url, **_engine_kwargs(database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

