"""Create only the configured application schema and apply migrations."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command


def main():
    cfg = get_settings()
    cfg.check_secrets()
    url = make_url(cfg.database_url)
    if url.get_backend_name() == "mysql":
        name = url.database
        if not name or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
            raise RuntimeError("开发库名称只允许字母、数字和下划线。")
        with create_engine(url.set(database=None), pool_pre_ping=True).begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    alembic = Config(str(ROOT / "backend/alembic.ini"))
    command.upgrade(alembic, "head")
    from app.db import SessionLocal
    from app.models import User
    from app.security import hasher

    if (
        len(cfg.bootstrap_admin_password) < 12
        or "CHANGE_ME" in cfg.bootstrap_admin_password
    ):
        raise RuntimeError("请先生成不少于12字符的初始管理员密码。")
    with SessionLocal() as db:
        if not db.scalar(
            select(User.id).where(User.username == cfg.bootstrap_admin_username)
        ):
            db.add(
                User(
                    username=cfg.bootstrap_admin_username,
                    name="系统管理员",
                    role="admin",
                    password_hash=hasher.hash(cfg.bootstrap_admin_password),
                )
            )
            db.commit()
    print(
        "Database migration and administrator initialization completed. Credentials remain in .env."
    )


if __name__ == "__main__":
    main()
