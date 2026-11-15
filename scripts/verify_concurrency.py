"""Verify MySQL SKIP LOCKED and unique batch results against the running application."""

import json
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings
from app.db import SessionLocal
from app.models import Analysis, JobItem
from verify_system import REPORT, checked, make_study

cfg = get_settings()
with httpx.Client(
    base_url="http://127.0.0.1:8000", trust_env=False, timeout=45
) as client:
    auth = checked(
        client.post(
            "/api/v1/auth/login",
            json=dict(
                username=cfg.bootstrap_admin_username,
                password=cfg.bootstrap_admin_password,
            ),
        )
    )
    client.headers["Authorization"] = "Bearer " + auth["access_token"]
    pid = checked(client.get("/api/v1/patients", params={"page_size": 100}))["items"][
        0
    ]["id"]
    ids = [
        make_study(client, pid, "signal", "并发领取验收 · " + str(i)) for i in range(4)
    ]
    job = checked(
        client.post(
            "/api/v1/jobs", json=dict(name="并发领取 · MySQL验收", study_ids=ids)
        )
    )
    with SessionLocal() as first, SessionLocal() as second:
        one = first.scalar(
            select(JobItem)
            .where(JobItem.job_id == job["id"], JobItem.status == "queued")
            .order_by(JobItem.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        two = second.scalar(
            select(JobItem)
            .where(JobItem.job_id == job["id"], JobItem.status == "queued")
            .order_by(JobItem.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        assert one and two and one.id != two.id, (
            "Different connections must not claim the same locked item"
        )
        first.rollback()
        second.rollback()
    for _ in range(60):
        result = checked(client.get("/api/v1/jobs/" + str(job["id"])))
        if result["status"] in ("succeeded", "partial", "failed"):
            break
        time.sleep(0.5)
    assert result["status"] == "succeeded", result
    with SessionLocal() as db:
        counts = dict(
            db.execute(
                select(Analysis.study_id, func.count())
                .where(Analysis.study_id.in_(ids))
                .group_by(Analysis.study_id)
            ).all()
        )
    assert all(counts.get(sid) == 1 for sid in ids)
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    report["mysql_concurrency"] = dict(
        passed=True,
        separate_connections=True,
        skip_locked=True,
        unique_results=True,
        items=4,
    )
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "PASS: MySQL separate-connection SKIP LOCKED and exactly one result for each of 4 batch items."
    )
