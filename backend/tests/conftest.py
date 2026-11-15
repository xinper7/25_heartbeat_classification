import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "runtime" / ("test-" + uuid.uuid4().hex)
TEST_ROOT.mkdir(parents=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (TEST_ROOT / "test.db").as_posix()
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "files")
os.environ["JWT_SECRET"] = "isolated-test-secret-" + "x" * 48
sys.path.insert(0, str(ROOT / "backend"))

from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hasher, token_for
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.state.login_hits = {}
    with SessionLocal() as db:
        for name, role in [
            ("admin", "admin"),
            ("analyst", "analyst"),
            ("other", "analyst"),
            ("reviewer", "reviewer"),
        ]:
            db.add(
                User(
                    username=name,
                    name=name,
                    role=role,
                    password_hash=hasher.hash("test-password-123!"),
                )
            )
        db.commit()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers():
    def get(name="admin"):
        from sqlalchemy import select

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == name))
            return {"Authorization": "Bearer " + token_for(user)}

    return get
