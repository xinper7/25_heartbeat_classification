import csv
import html
import io
import time
from datetime import timedelta

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .inference import get_engine
from .models import Analysis, Audit, Job, JobItem, Patient, Review, Study, User, now


def audit(db, actor, action, target, request_id=""):
    db.add(
        Audit(
            actor_id=actor.id if actor else None,
            action=action,
            target=str(target),
            request_id=request_id,
        )
    )


def access_patient(db, patient_id, user):
    p = db.get(Patient, patient_id)
    if not p or (user.role == "analyst" and p.owner_id != user.id):
        raise HTTPException(404, "档案不存在或无访问权限")
    return p


def access_study(db, study_id, user, lock=False):
    query = select(Study).where(Study.id == study_id)
    if lock:
        query = query.with_for_update()
    study = db.scalar(query)
    if not study or (user.role == "analyst" and study.owner_id != user.id):
        raise HTTPException(404, "检查不存在或无访问权限")
    return study


def serialize_study(db, study):
    patient = db.get(Patient, study.patient_id)
    return dict(
        id=study.id,
        patient_id=study.patient_id,
        patient_name=patient.name,
        patient_code=patient.code,
        title=study.title,
        kind=study.kind,
        status=study.status,
        note=study.note,
        metadata=study.metadata_json,
        error=study.error,
        created_at=study.created_at.isoformat() + "Z",
        updated_at=study.updated_at.isoformat() + "Z",
    )


def serialize_analysis(db, analysis):
    history = db.scalars(
        select(Review)
        .where(Review.analysis_id == analysis.id)
        .order_by(Review.id.desc())
    ).all()
    review = history[0] if history else None
    reviewer = db.get(User, review.reviewer_id) if review else None
    return dict(
        id=analysis.id,
        study_id=analysis.study_id,
        model_version=analysis.model_version,
        preprocessing_version=analysis.preprocessing_version,
        predictions=analysis.predictions,
        timings=analysis.timings,
        provenance=analysis.provenance,
        created_at=analysis.created_at.isoformat() + "Z",
        review=dict(
            comment=review.comment,
            conclusion=review.conclusion,
            reviewer=reviewer.name,
            created_at=review.created_at.isoformat() + "Z",
        )
        if review
        else None,
        review_history=[
            dict(
                comment=r.comment,
                conclusion=r.conclusion,
                reviewer=db.get(User, r.reviewer_id).name,
                created_at=r.created_at.isoformat() + "Z",
            )
            for r in history
        ],
    )


def perform_analysis(db: Session, study_id: int, user_id: int, claim_token=None):
    user = db.get(User, user_id)
    study = access_study(db, study_id, user, lock=True)
    if claim_token:
        item = db.scalar(
            select(JobItem).where(JobItem.claim_token == claim_token).with_for_update()
        )
        if not item or item.status != "running" or item.study_id != study.id:
            raise HTTPException(409, "任务租约已失效")
        if item.analysis_id:
            return db.get(Analysis, item.analysis_id)
    if not study.metadata_json.get("storage_key"):
        raise HTTPException(400, "请先上传并校验数据")
    allowed_statuses = ("queued",) if claim_token else ("ready", "failed")
    if study.status not in allowed_statuses:
        raise HTTPException(409, "检查当前状态不允许重复分析")
    study.status = "processing"
    study.error = ""
    study.updated_at = now()
    db.commit()
    started = time.perf_counter()
    try:
        folder = (
            get_settings().storage_dir / "uploads" / study.metadata_json["storage_key"]
        )
        array = np.load(folder / "input.npy", allow_pickle=False)
        loaded = time.perf_counter()
        result = get_engine().predict(study.kind, array)
        done = time.perf_counter()
        # Recheck lease under lock before persisting. A recovered job cannot commit stale results.
        if claim_token:
            item = db.scalar(
                select(JobItem)
                .where(JobItem.claim_token == claim_token)
                .with_for_update()
            )
            if not item or item.status != "running":
                raise HTTPException(409, "任务已由其他执行进程接管")
        timings = result["timings"] | dict(
            input_load_ms=round((loaded - started) * 1000, 3),
            service_ms=round((done - started) * 1000, 3),
        )
        analysis = Analysis(
            study_id=study.id,
            model_version=result["model_version"],
            preprocessing_version=study.metadata_json["preprocessing_version"],
            predictions=result["predictions"],
            timings=timings,
            provenance=result["provenance"]
            | {
                "input_profile": study.metadata_json.get(
                    "input_profile", "report_image"
                )
            },
        )
        db.add(analysis)
        db.flush()
        study.status = "awaiting_review"
        if claim_token:
            item.analysis_id = analysis.id
            item.status = "succeeded"
            item.lease_until = None
        audit(db, user, "analysis.completed", f"analysis:{analysis.id}")
        db.commit()
        return analysis
    except Exception as exc:
        db.rollback()
        study = db.get(Study, study_id)
        if claim_token:
            item = db.scalar(
                select(JobItem)
                .where(JobItem.claim_token == claim_token)
                .with_for_update()
            )
            if not item or item.status != "running":
                raise
        if isinstance(exc, BlockingIOError):
            study.status = "queued" if claim_token else "ready"
            db.commit()
            raise HTTPException(429, str(exc)) from exc
        if study.status == "processing":
            study.status = "failed"
            study.error = "分析未完成，请检查模型状态后重试。"
        audit(db, user, "analysis.failed", f"study:{study_id}")
        db.commit()
        raise


def job_result(db, job):
    items = db.scalars(
        select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)
    ).all()
    counts = {
        s: sum(i.status == s for i in items)
        for s in ("queued", "running", "succeeded", "failed")
    }
    return dict(
        id=job.id,
        name=job.name,
        status=job.status,
        created_at=job.created_at.isoformat() + "Z",
        counts=counts,
        total=len(items),
        progress=round(
            (counts["succeeded"] + counts["failed"]) / max(1, len(items)) * 100
        ),
        items=[
            dict(
                id=i.id,
                study_id=i.study_id,
                status=i.status,
                attempts=i.attempts,
                error=i.error,
                analysis_id=i.analysis_id,
            )
            for i in items
        ],
    )


def refresh_job(db, job_id):
    job = db.get(Job, job_id)
    states = list(db.scalars(select(JobItem.status).where(JobItem.job_id == job_id)))
    if any(s in ("queued", "running") for s in states):
        job.status = "running" if "running" in states else "queued"
    elif all(s == "succeeded" for s in states):
        job.status = "succeeded"
    elif any(s == "succeeded" for s in states):
        job.status = "partial"
    else:
        job.status = "failed"


def recover_stale(db):
    expired = db.scalars(
        select(JobItem)
        .where(JobItem.status == "running", JobItem.lease_until < now())
        .with_for_update(skip_locked=True)
    ).all()
    recovered_studies = set()
    for item in expired:
        study = db.get(Study, item.study_id)
        item.claim_token = None
        item.lease_until = None
        if item.analysis_id:
            item.status = "succeeded"
        elif item.attempts >= 3:
            item.status = "failed"
            item.error = "执行进程中断且已达到自动恢复次数，请人工重试。"
            study.status = "failed"
        else:
            item.status = "queued"
            study.status = "queued"
        recovered_studies.add(study.id)
        refresh_job(db, item.job_id)
    # Sync requests interrupted by a stopped API process must also be recoverable.
    cutoff = now() - timedelta(seconds=get_settings().job_lease_seconds)
    studies = db.scalars(
        select(Study).where(Study.status == "processing", Study.updated_at < cutoff)
    ).all()
    for study in studies:
        active = db.scalar(
            select(JobItem.id).where(
                JobItem.study_id == study.id, JobItem.status == "running"
            )
        )
        if not active and study.id not in recovered_studies:
            study.status = "failed"
            study.error = "上次分析被中断，可以重新提交。"
    db.commit()


def export_csv(db, studies):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "检查编号",
            "受检者编号",
            "检查名称",
            "输入类型",
            "状态",
            "模型版本",
            "预测标签",
            "纯推理毫秒",
            "复核意见",
        ]
    )

    def safe(value):
        text = str(value)
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

    for study in studies:
        analysis = db.scalar(
            select(Analysis)
            .where(Analysis.study_id == study.id)
            .order_by(Analysis.id.desc())
        )
        review = (
            db.scalar(
                select(Review)
                .where(Review.analysis_id == analysis.id)
                .order_by(Review.id.desc())
            )
            if analysis
            else None
        )
        patient = db.get(Patient, study.patient_id)
        writer.writerow(
            [
                study.id,
                safe(patient.code),
                safe(study.title),
                study.kind,
                study.status,
                analysis.model_version if analysis else "",
                ", ".join(p["code"] for p in analysis.predictions if p["positive"])
                if analysis
                else "",
                analysis.timings["inference_ms"] if analysis else "",
                safe(review.comment) if review else "",
            ]
        )
    return "\ufeff" + stream.getvalue()


def report_html(db, study, analysis):
    patient = db.get(Patient, study.patient_id)
    data = serialize_analysis(db, analysis)
    esc = lambda x: html.escape(str(x))
    rows = "".join(
        f"<tr><td>{esc(p['code'])} · {esc(p['name'])}</td><td>{p['probability']:.4f}</td><td>{p['threshold']:.2f}</td><td>{'阳性' if p['positive'] else '阴性'}</td></tr>"
        for p in analysis.predictions
    )
    review = data["review"]
    review_text = (
        f"{esc(review['reviewer'])} · {esc(review['created_at'])}<p>{esc(review['comment'])}</p>"
        if review
        else "尚未复核"
    )
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>心电分析报告 {study.id}</title><style>body{{font:15px/1.8 "Microsoft YaHei",sans-serif;color:#163039;max-width:860px;margin:40px auto;padding:0 24px}}h1{{font-size:26px}}h2{{font-size:18px;margin-top:30px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #d9e2e6;padding:12px;text-align:left}}.muted{{color:#647880}}.meta{{background:#f2f7f7;padding:20px}}@media print{{button{{display:none}}body{{margin:0;max-width:none}}}}</style><button onclick="window.print()">打印 / 保存为PDF</button><p class="muted">CARDIO WORKSPACE · 检查与分析记录</p><h1>心电分析报告</h1><div class="meta">检查编号：ECG-{study.id:05d}<br>受检者：{esc(patient.name)}（{esc(patient.code)}）<br>检查名称：{esc(study.title)}<br>输入方式：{"数字心电信号" if study.kind == "signal" else "标准报告图"}<br>生成时间：{esc(data["created_at"])}</div><h2>模型分类结果</h2><table><tr><th>诊断超类</th><th>预测概率</th><th>固定阈值</th><th>模型判定</th></tr>{rows}</table><p class="muted">输出为五类多标签预测，可同时出现多个阳性标签。概率不是诊断准确率。</p><h2>专业人员复核</h2><div>{review_text}</div><h2>模型与处理信息</h2><p>模型：{esc(analysis.model_version)}<br>预处理：{esc(analysis.preprocessing_version)}<br>纯推理：{analysis.timings["inference_ms"]:.2f} ms<br>模型SHA-256：{esc(analysis.provenance["model_sha256"])}</p><p class="muted">本报告记录模型辅助分析与人员复核意见，二者独立保存。</p></html>"""
