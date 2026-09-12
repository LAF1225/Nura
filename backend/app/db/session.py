"""Database engine and session handling.

Deliberately synchronous SQLAlchemy. FastAPI runs synchronous endpoints in a
worker threadpool, which is plenty for this workload, and sync sessions are
markedly easier to read and debug than the async variants -- see
docs/decisions/0002-fastapi-postgresql.md.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    # Verifies a pooled connection is still alive before handing it out, which
    # avoids stale-connection errors after the database restarts or idles out.
    pool_pre_ping=True,
    echo=False,
)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed.

    Usage::

        @router.get("/example")
        def example(db: Session = Depends(get_db)) -> ...:
            ...
    """
    with SessionFactory() as session:
        yield session
