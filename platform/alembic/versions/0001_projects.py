"""Create durable platform projects."""
from alembic import op
import sqlalchemy as sa

revision = "0001_projects"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_projects_name_length"),
        sa.CheckConstraint("length(requirements) BETWEEN 20 AND 50000", name="ck_projects_requirements_length"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("projects")
