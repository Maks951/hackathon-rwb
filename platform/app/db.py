import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL (postgresql+psycopg://...) before starting")
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    # A new Session for each request; never share it between threads.
    with get_session_factory()() as session:
        yield session
