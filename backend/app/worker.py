"""Durable MySQL task worker. Start separately: python -m app.worker."""

import logging
import threading
import time
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from .config import get_settings
from .db import SessionLocal
from .inference import get_engine
from .models import JobItem, Study, now
from .services import perform_analysis, recover_stale, refresh_job

log = logging.getLogger("ecg.worker")


def heartbeat(token, stopped):
    seconds = get_settings().job_lease_seconds
    while not stopped.wait(max(2, seconds / 3)):
        try:
            with SessionLocal() as db:
                db.execute(
                    update(JobItem)
                    .where(JobItem.claim_token == token, JobItem.status == "running")
                    .values(lease_until=now() + timedelta(seconds=seconds))
                )
                db.commit()
        except Exception:
            log.exception("heartbeat_failed")


def run_once():
    from .models import Job

    with SessionLocal() as db:
        recover_stale(db)
        item = db.scalar(
            select(JobItem)
            .where(JobItem.status == "queued")
            .order_by(JobItem.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not item:
            return False
        item.status = "running"
        item.attempts += 1
        item.claim_token = uuid.uuid4().hex
        item.lease_until = now() + timedelta(seconds=get_settings().job_lease_seconds)
        token, study_id, job_id = item.claim_token, item.study_id, item.job_id
        owner_id = db.get(Job, job_id).owner_id
        refresh_job(db, job_id)
        db.commit()
    stopped = threading.Event()
    ticker = threading.Thread(target=heartbeat, args=(token, stopped), daemon=True)
    ticker.start()
    try:
        with SessionLocal() as db:
            perform_analysis(db, study_id, owner_id, token)
    except Exception as exc:
        log.exception("job_item_failed job=%s study=%s", job_id, study_id)
        with SessionLocal() as db:
            item = db.scalar(
                select(JobItem).where(JobItem.claim_token == token).with_for_update()
            )
            if item and item.status == "running":
                if isinstance(exc, HTTPException) and exc.status_code == 429:
                    item.status = "queued"
                    item.attempts -= 1
                    db.get(Study, study_id).status = "queued"
                else:
                    item.status = "failed"
                    item.error = "分析失败，请检查服务日志、模型状态和输入后重试。"
                    db.get(Study, study_id).status = "failed"
                item.lease_until = None
                db.commit()
    finally:
        stopped.set()
        ticker.join(timeout=2)
        with SessionLocal() as db:
            refresh_job(db, job_id)
            db.commit()
    return True


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    get_settings().check_secrets()
    get_engine().warmup()
    log.info(
        "Worker ready; MySQL durable queue, model threads=%s",
        get_settings().model_threads,
    )
    try:
        while True:
            try:
                worked = run_once()
            except Exception:
                log.exception("worker_loop_failed")
                worked = False
            time.sleep(0.1 if worked else get_settings().worker_poll_seconds)
    except KeyboardInterrupt:
        log.info("Worker stopped; leased tasks will be recovered after lease expiry.")


if __name__ == "__main__":
    main()
