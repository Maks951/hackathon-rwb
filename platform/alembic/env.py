import os
from alembic import context
from sqlalchemy import create_engine, pool
from app.models.project import Base
from app.models.step import Step
from app.models.run import Run
from app.models.run_event import RunEvent

target_metadata = Base.metadata
url = os.environ["DATABASE_URL"]

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
