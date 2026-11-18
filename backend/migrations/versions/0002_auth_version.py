"""Invalidate earlier sessions when an account password changes."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # 0001 creates tables from current metadata on fresh installations.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "auth_version" not in columns:
        op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "auth_version")
