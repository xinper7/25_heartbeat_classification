from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from app.config import ROOT, get_settings


def test_auth_version_migration_preserves_existing_users(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "legacy.db").as_posix()
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64))"))
        connection.execute(text("INSERT INTO users VALUES (7, 'existing')"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    monkeypatch.setattr(get_settings(), "database_url", url)
    config = Config(str(ROOT / "backend/alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT username, auth_version FROM users WHERE id=7")).one() == ('existing', 0)
    engine.dispose()


def test_fresh_migrations_include_auth_version(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    monkeypatch.setattr(get_settings(), "database_url", url)
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    engine = create_engine(url)
    assert "auth_version" in {column['name'] for column in inspect(engine).get_columns('users')}
    engine.dispose()
