"""Register generated artifact metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0005_artifacts"
down_revision = "f04c10b9b51e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("step_id", sa.Uuid(), sa.ForeignKey("steps.id"), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifacts_size"),
        sa.UniqueConstraint("run_id", "path", name="uq_artifacts_run_path"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_step_id", "artifacts", ["step_id"])


def downgrade():
    op.drop_table("artifacts")
