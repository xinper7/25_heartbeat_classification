"""Initial relational schema."""

from alembic import op
from app.db import Base
from app import models

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    raise RuntimeError("自动删表被禁用；请先备份并显式编写数据迁移。")
