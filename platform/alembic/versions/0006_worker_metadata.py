"""Persist worker step metadata and authoritative package reference."""

import sqlalchemy as sa

from alembic import op

revision = "0006_worker_metadata"
down_revision = "0005_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "steps", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column("runs", sa.Column("package_path", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("runs", "package_path")
    op.drop_column("steps", "metadata_json")
