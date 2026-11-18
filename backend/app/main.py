import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .config import ROOT, get_settings
from .db import SessionLocal, get_db
from .inference import get_engine
from .inputs import InputError, LEADS, prepare_image, prepare_signal
from .models import (
    Analysis,
    Asset,
    Audit,
    Job,
    JobItem,
    Patient,
    Review,
    Study,
    User,
    now,
)
from .schemas import (
    ApiResponse,
    JobIn,
    LoginIn,
    PasswordIn,
    PatientIn,
    ReviewAction,
    ReviewIn,
    StudyIn,
    UserIn,
    UserUpdate,
)
from . import samples as sample_names
from .security import current_user, hasher, require_roles, token_for, verify_password
from .services import (
    access_patient,
    access_study,
    audit,
    export_csv,
    job_result,
    report_html,
    serialize_analysis,
    serialize_study,
)
from .services import perform_analysis

from .version import REVISION, STARTED_AT

log = logging.getLogger("ecg")
cfg = get_settings()
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(current_user)]
Analyst = Annotated[User, Depends(require_roles("analyst", "admin"))]
Reviewer = Annotated[User, Depends(require_roles("reviewer", "admin"))]
Admin = Annotated[User, Depends(require_roles("admin"))]


def ok(result=None, msg="成功", status=200):
    return JSONResponse(
        jsonable_encoder(dict(code=0, result=result, msg=msg)), status_code=status
    )


@asynccontextmanager
async def lifespan(app):
    cfg.check_secrets()
    cfg.storage_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    get_engine().warmup()
    from .agent_lab import start_warmup
    start_warmup()
    yield


app = FastAPI(
    title="Cardio Workspace 心电检查与分析平台",
    version="1.0.0",
    lifespan=lifespan,
    description="面向专业人员的数字心电信号与标准报告图独立分析服务。业务账号角色：analyst、reviewer、admin。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in cfg.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def timing_middleware(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Server-Timing"] = (
        f"app;dur={(time.perf_counter() - start) * 1000:.2f}"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        dict(
            code=exc.status_code,
            result=None,
            msg=str(exc.detail),
            request_id=getattr(request.state, "request_id", ""),
        ),
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    details = [
        {"field": ".".join(str(v) for v in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        dict(code=422, result=details, msg="输入参数不符合要求，请检查表单。"),
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    return JSONResponse(
        dict(code=409, result=None, msg="编号或账号已存在，或操作与关联数据冲突。"),
        status_code=409,
    )


@app.exception_handler(Exception)
async def server_error(request, exc):
    log.exception("request_failed id=%s", getattr(request.state, "request_id", ""))
    return JSONResponse(
        dict(
            code=500,
            result=None,
            msg="处理未完成，请稍后重试或联系管理员。",
            request_id=getattr(request.state, "request_id", ""),
        ),
        status_code=500,
    )


@app.get("/api/v1/health", tags=["system"], response_model=ApiResponse)
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = True
    except SQLAlchemyError:
        database = False
    engine = get_engine()
    ready = database and len(engine.models) == 2
    return ok(
        dict(
            ready=ready,
            database=database,
            models={k: k in engine.models for k in ("signal", "image")},
            version="1.0.0",
            revision=REVISION,
            started_at=STARTED_AT,
        ),
        status=200 if ready else 503,
    )


@app.post("/api/v1/auth/login", tags=["auth"], response_model=ApiResponse)
def login(body: LoginIn, db: DB, request: Request):
    # Local service throttle; reverse-proxy rate limiting may be added for public deployment.
    key = request.client.host if request.client else "local"
    hits = getattr(app.state, "login_hits", {})
    recent = [t for t in hits.get(key, []) if time.monotonic() - t < 60]
    if len(recent) >= 15:
        raise HTTPException(429, "登录尝试过于频繁，请稍后再试。")
    hits[key] = recent + [time.monotonic()]
    app.state.login_hits = hits
    user = db.scalar(select(User).where(User.username == body.username))
    if (
        not user
        or not verify_password(body.password, user.password_hash)
        or not user.active
    ):
        raise HTTPException(401, "账号或密码不正确")
    audit(db, user, "auth.login", "user:" + str(user.id), request.state.request_id)
    db.commit()
    return ok(
        dict(access_token=token_for(user), token_type="bearer", user=user_view(user))
    )


def user_view(user):
    return dict(
        id=user.id,
        username=user.username,
        name=user.name,
        role=user.role,
        active=user.active,
    )


@app.get("/api/v1/auth/me", tags=["auth"], response_model=ApiResponse)
def me(user: Actor):
    return ok(user_view(user))


@app.post("/api/v1/auth/password", tags=["auth"], response_model=ApiResponse)
def password(body: PasswordIn, db: DB, user: Actor):
    user = db.scalar(
        select(User).where(User.id == user.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    user.password_hash = hasher.hash(body.new_password)
    user.auth_version += 1
    audit(db, user, "auth.password_changed", "user:" + str(user.id))
    db.commit()
    return ok(msg="密码已更新")


@app.get("/api/v1/users", tags=["admin"], response_model=ApiResponse)
def users(db: DB, user: Admin):
    return ok([user_view(u) for u in db.scalars(select(User).order_by(User.id))])


@app.post("/api/v1/users", tags=["admin"], response_model=ApiResponse)
def create_user(body: UserIn, db: DB, user: Admin):
    record = User(
        username=body.username,
        name=body.name,
        role=body.role,
        password_hash=hasher.hash(body.password),
    )
    db.add(record)
    db.flush()
    audit(db, user, "user.created", "user:" + str(record.id))
    db.commit()
    return ok(user_view(record), status=201)


@app.patch("/api/v1/users/{user_id}", tags=["admin"], response_model=ApiResponse)
def edit_user(user_id: int, body: UserUpdate, db: DB, user: Admin):
    record = db.get(User, user_id)
    if not record:
        raise HTTPException(404, "账号不存在")
    if record.id == user.id and (
        body.active is False or body.role not in (None, "admin")
    ):
        raise HTTPException(409, "不能停用自己或移除自己的管理员角色")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    audit(db, user, "user.updated", "user:" + str(record.id))
    db.commit()
    return ok(user_view(record))


@app.get("/api/v1/patients", tags=["patients"], response_model=ApiResponse)
def patients(db: DB, user: Actor, q: str = "", page: int = 1, page_size: int = 20):
    page, page_size = max(1, page), max(1, min(100, page_size))
    query = select(Patient)
    if user.role == "analyst":
        query = query.where(Patient.owner_id == user.id)
    if q:
        query = query.where(
            or_(
                Patient.name.contains(q[:100], autoescape=True),
                Patient.code.contains(q[:100], autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Patient.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ok(
        dict(
            items=[
                dict(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    sex=p.sex,
                    age=p.age,
                    note=p.note,
                    created_at=p.created_at.isoformat() + "Z",
                )
                for p in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@app.post("/api/v1/patients", tags=["patients"], response_model=ApiResponse)
def create_patient(body: PatientIn, db: DB, user: Analyst):
    patient = Patient(**body.model_dump(), owner_id=user.id)
    db.add(patient)
    db.flush()
    audit(db, user, "patient.created", "patient:" + str(patient.id))
    db.commit()
    return ok(dict(id=patient.id), status=201)


@app.put("/api/v1/patients/{patient_id}", tags=["patients"], response_model=ApiResponse)
def edit_patient(patient_id: int, body: PatientIn, db: DB, user: Analyst):
    patient = access_patient(db, patient_id, user)
    for key, value in body.model_dump().items():
        setattr(patient, key, value)
    audit(db, user, "patient.updated", "patient:" + str(patient.id))
    db.commit()
    return ok(dict(id=patient.id))


@app.delete(
    "/api/v1/patients/{patient_id}", tags=["patients"], response_model=ApiResponse
)
def delete_patient(patient_id: int, db: DB, user: Analyst):
    patient = access_patient(db, patient_id, user)
    if db.scalar(select(Study.id).where(Study.patient_id == patient.id).limit(1)):
        raise HTTPException(409, "档案已有检查记录，需要保留关联历史。")
    db.delete(patient)
    audit(db, user, "patient.deleted", "patient:" + str(patient_id))
    db.commit()
    return ok()


def filtered_studies(db, user, q="", kind="", status="", source="", patient_id=None, date_from=None, date_to=None):
    query = select(Study).join(Patient)
    if user.role == "analyst":
        query = query.where(Study.owner_id == user.id)
    if q:
        numeric=q.strip().upper().removeprefix('ECG-').lstrip('#')
        if numeric.isdigit():
            query=query.where(Study.id==int(numeric))
            q=''
    if q:
        query = query.where(
            or_(
                Study.title.contains(q[:100], autoescape=True),
                Patient.code.contains(q[:100], autoescape=True),
                Patient.name.contains(q[:100], autoescape=True),
            )
        )
    if kind:
        query = query.where(Study.kind == kind)
    if status:
        query = query.where(Study.status == status)
    sample_purpose=Study.metadata_json["source"]["purpose"].as_string()
    if source=="sample":query=query.where(sample_purpose=="public_sample")
    elif source=="regular":query=query.where(or_(sample_purpose.is_(None),sample_purpose!="public_sample"))
    if patient_id:
        access_patient(db, patient_id, user)
        query = query.where(Study.patient_id == patient_id)
    if date_from:
        date_from = (
            date_from.astimezone(timezone.utc).replace(tzinfo=None)
            if date_from.tzinfo
            else date_from
        )
        query = query.where(Study.created_at >= date_from)
    if date_to:
        date_to = (
            date_to.astimezone(timezone.utc).replace(tzinfo=None)
            if date_to.tzinfo
            else date_to
        )
        query = query.where(Study.created_at <= date_to)
    return query


@app.get("/api/v1/studies", tags=["studies"], response_model=ApiResponse)
def studies(
    db: DB,
    user: Actor,
    q: str = "",
    kind: str = "",
    status: str = "",
    source: str = "",
    patient_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
):
    page, page_size = max(1, page), max(1, min(100, page_size))
    query = filtered_studies(db,user,q,kind,status,source,patient_id,date_from,date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Study.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ok(
        dict(
            items=[serialize_study(db, s) for s in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@app.post("/api/v1/studies", tags=["studies"], response_model=ApiResponse)
def create_study(body: StudyIn, db: DB, user: Analyst):
    access_patient(db, body.patient_id, user)
    study = Study(**body.model_dump(), owner_id=user.id)
    db.add(study)
    db.flush()
    audit(db, user, "study.created", "study:" + str(study.id))
    db.commit()
    return ok(serialize_study(db, study), status=201)


@app.get("/api/v1/studies/{study_id}", tags=["studies"], response_model=ApiResponse)
def study_detail(study_id: int, db: DB, user: Actor):
    study = access_study(db, study_id, user)
    analyses = db.scalars(
        select(Analysis)
        .where(Analysis.study_id == study.id)
        .order_by(Analysis.id.desc())
    ).all()
    return ok(
        serialize_study(db, study)
        | dict(analyses=[serialize_analysis(db, a) for a in analyses])
    )


@app.post(
    "/api/v1/studies/{study_id}/assets", tags=["studies"], response_model=ApiResponse
)
def upload_assets(
    study_id: int,
    db: DB,
    user: Analyst,
    files: list[UploadFile] = File(...),
    profile: str = Form("filtered_mv"),
    sampling_rate: int = Form(100),
    unit: str = Form("mV"),
):
    study = access_study(db, study_id, user, lock=True)
    if study.status != "awaiting_upload":
        raise HTTPException(
            409, "该检查已上传数据。请新建检查，保留既有输入及分析记录。"
        )
    if not 1 <= len(files) <= 2:
        raise HTTPException(400, "最多上传两个配对文件")
    contents = {}
    max_bytes = cfg.max_upload_mb * 1024 * 1024
    total = 0
    for upload in files:
        name = upload.filename or ""
        if (
            not name
            or len(name) > 200
            or name != Path(name).name
            or "/" in name
            or "\\" in name
            or name in contents
        ):
            raise HTTPException(400, "文件名无效或重复")
        data = upload.file.read(max_bytes + 1)
        total += len(data)
        if total > max_bytes:
            raise HTTPException(413, f"单次上传总大小不能超过{cfg.max_upload_mb} MB")
        contents[name] = data
    try:
        if study.kind == "signal":
            array, meta = prepare_signal(contents, profile, sampling_rate, unit)
            image = None
        else:
            image, array, meta = prepare_image(contents)
    except InputError as exc:
        raise HTTPException(400, str(exc)) from exc
    key = uuid.uuid4().hex
    folder = cfg.storage_dir / "uploads" / key
    folder.mkdir(parents=True)
    for name, data in contents.items():
        stored_name = uuid.uuid4().hex + Path(name).suffix.lower()
        (folder / stored_name).write_bytes(data)
        db.add(
            Asset(
                study_id=study.id,
                original_name=name,
                stored_name=stored_name,
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
            )
        )
    np.save(folder / "input.npy", array, allow_pickle=False)
    if image is not None:
        image.thumbnail((1800, 1800))
        image.save(folder / "preview.png")
    detected_source=sample_names.source_for_hashes(hashlib.sha256(data).hexdigest() for data in contents.values())
    study.metadata_json = meta | {"storage_key": key, "files": list(contents)} | ({"source":detected_source} if detected_source else {})
    study.status = "ready"
    audit(db, user, "assets.uploaded", "study:" + str(study.id))
    db.commit()
    return ok(serialize_study(db, study), "数据已校验，可开始分析")


@app.get("/api/v1/studies/{study_id}/preview", tags=["studies"])
def preview(study_id: int, db: DB, user: Actor):
    study = access_study(db, study_id, user)
    key = study.metadata_json.get("storage_key")
    if not key:
        raise HTTPException(404, "尚未上传数据")
    folder = cfg.storage_dir / "uploads" / key
    if study.kind == "image":
        return FileResponse(folder / "preview.png", media_type="image/png")
    array = np.load(folder / "input.npy", allow_pickle=False)
    return ok(
        dict(
            leads=LEADS,
            times=(np.arange(1000) / 100).tolist(),
            values=array.tolist(),
            unit="mV",
        )
    )


@app.post(
    "/api/v1/studies/{study_id}/analyses", tags=["analyses"], response_model=ApiResponse
)
def analyze(study_id: int, db: DB, user: Analyst):
    analysis = perform_analysis(db, study_id, user.id)
    return ok(
        serialize_analysis(db, analysis), "分析完成，等待专业人员复核", status=201
    )


@app.post(
    "/api/v1/analyses/{analysis_id}/reviews",
    tags=["reviews"],
    response_model=ApiResponse,
)
def review(analysis_id: int, body: ReviewIn, db: DB, user: Reviewer):
    return save_review_action(db, user, analysis_id, body, body.conclusion)


@app.post("/api/v1/analyses/{analysis_id}/resubmit", tags=["reviews"], response_model=ApiResponse)
def resubmit(analysis_id: int, body: ReviewAction, db: DB, user: Analyst):
    return save_review_action(db, user, analysis_id, body, "resubmitted")


def save_review_action(db, user, analysis_id, body, action):
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "分析记录不存在")
    study = access_study(db, analysis.study_id, user, lock=True)
    latest = db.scalar(select(Analysis.id).where(Analysis.study_id == study.id)
                       .order_by(Analysis.id.desc()).limit(1).with_for_update())
    previous = db.scalar(select(Review.id).where(Review.analysis_id == analysis_id)
                         .order_by(Review.id.desc()).limit(1).with_for_update())
    required = "pending_correction" if action == "resubmitted" else "awaiting_review"
    if latest != analysis_id or study.status != required or previous != body.previous_event_id:
        raise HTTPException(409, "检查状态或复核记录已更新，请刷新后重试")
    comment = body.comment.strip()
    if len(comment) < 5:
        raise HTTPException(422, "请填写至少五个字符的说明")
    db.add(Review(analysis_id=analysis_id, reviewer_id=user.id, conclusion=action, comment=comment))
    study.status = {"returned": "pending_correction", "resubmitted": "awaiting_review"}.get(action, "archived")
    audit(db, user, "review." + action, "analysis:" + str(analysis.id))
    db.commit()
    return ok(serialize_analysis(db, analysis), "操作已保存")


@app.get("/api/v1/analyses/{analysis_id}/report", tags=["reports"])
def report(analysis_id: int, db: DB, user: Actor):
    analysis = db.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(404, "分析记录不存在")
    study = access_study(db, analysis.study_id, user)
    from .pdf_report import report_pdf
    return Response(report_pdf(db, study, analysis), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="ecg-report-{analysis.id}.pdf"',
        "Cache-Control": "no-store",
    })


@app.get("/api/v1/exports/studies.csv", tags=["reports"])
def export_studies(db: DB, user: Actor, q: str="", kind: str="", status: str="", source: str="", patient_id: int|None=None, date_from: datetime|None=None, date_to: datetime|None=None):
    query=filtered_studies(db,user,q,kind,status,source,patient_id,date_from,date_to)
    rows = db.scalars(query.order_by(Study.id.desc())).all()
    return Response(
        export_csv(db, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ecg-studies.csv"'},
    )


@app.post("/api/v1/jobs", tags=["jobs"], response_model=ApiResponse)
def create_job(body: JobIn, db: DB, user: Analyst):
    ids = sorted(set(body.study_ids))
    selected = [access_study(db, sid, user, lock=True) for sid in ids]
    if any(
        s.status not in ("ready", "failed") or not s.metadata_json.get("storage_key")
        for s in selected
    ):
        raise HTTPException(409, "批次仅接收已校验或分析失败的检查，不能重复排队。")
    job = Job(owner_id=user.id, name=body.name)
    db.add(job)
    db.flush()
    for study in selected:
        study.status = "queued"
        db.add(JobItem(job_id=job.id, study_id=study.id))
    audit(db, user, "job.created", "job:" + str(job.id))
    db.commit()
    return ok(job_result(db, job), "任务已排队，由独立Worker执行", status=202)


@app.get("/api/v1/jobs", tags=["jobs"], response_model=ApiResponse)
def jobs(db: DB, user: Actor):
    query = select(Job)
    if user.role == "analyst":
        query = query.where(Job.owner_id == user.id)
    return ok(
        [job_result(db, j) for j in db.scalars(query.order_by(Job.id.desc()).limit(50))]
    )


def access_job(db, job_id, user):
    job = db.get(Job, job_id)
    if not job or (user.role == "analyst" and job.owner_id != user.id):
        raise HTTPException(404, "任务不存在或无访问权限")
    return job


@app.get("/api/v1/jobs/{job_id}", tags=["jobs"], response_model=ApiResponse)
def job_detail(job_id: int, db: DB, user: Actor):
    return ok(job_result(db, access_job(db, job_id, user)))


@app.post("/api/v1/jobs/{job_id}/retries", tags=["jobs"], response_model=ApiResponse)
def retry_job(job_id: int, db: DB, user: Analyst):
    job = access_job(db, job_id, user)
    items = db.scalars(
        select(JobItem)
        .where(JobItem.job_id == job.id, JobItem.status == "failed")
        .with_for_update()
    ).all()
    if not items:
        raise HTTPException(409, "没有可重试的失败项")
    for item in items:
        study = access_study(db, item.study_id, user, lock=True)
        if study.status != "failed":
            raise HTTPException(409, "部分检查已在其他任务中处理，不能重复重试")
        item.status, item.error, item.attempts, item.claim_token, item.lease_until = (
            "queued",
            "",
            0,
            None,
            None,
        )
        study.status = "queued"
    job.status = "queued"
    audit(db, user, "job.retried", "job:" + str(job.id))
    db.commit()
    return ok(job_result(db, job))


@app.get("/api/v1/dashboard", tags=["dashboard"], response_model=ApiResponse)
def dashboard(db: DB, user: Actor):
    query = select(Study)
    pquery = select(func.count(Patient.id))
    if user.role == "analyst":
        query = query.where(Study.owner_id == user.id)
        pquery = pquery.where(Patient.owner_id == user.id)
    counts = dict(
        db.execute(
            select(Study.status, func.count())
            .where(Study.id.in_(select(query.subquery().c.id)))
            .group_by(Study.status)
        ).all()
    )
    recent = db.scalars(query.order_by(Study.id.desc()).limit(6)).all()
    return ok(
        dict(
            patient_count=db.scalar(pquery),
            study_count=sum(counts.values()),
            counts=counts,
            recent=[serialize_study(db, s) for s in recent],
            models_ready={k: k in get_engine().models for k in ("signal", "image")},
        )
    )


@app.get("/api/v1/models", tags=["models"], response_model=ApiResponse)
def models(user: Actor):
    engine = get_engine()
    return ok(
        [
            dict(
                kind=k,
                **info,
                loaded=k in engine.models,
                error="模型加载失败，请查看本地服务日志" if k in engine.errors else "",
            )
            for k, info in engine.manifest.items()
        ]
    )


@app.get("/api/v1/audit", tags=["admin"], response_model=ApiResponse)
def audit_logs(db: DB, user: Admin, page: int = 1, q: str = ""):
    query = select(Audit)
    if q.strip():
        term = q.strip()[:100]
        conditions = [Audit.action.contains(term, autoescape=True), Audit.target.contains(term, autoescape=True)]
        if term.isdigit(): conditions.append(Audit.actor_id == int(term))
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query
        .order_by(Audit.id.desc())
        .offset((max(1, page) - 1) * 50)
        .limit(50)
    ).all()
    return ok(
        dict(
            items=[
                dict(
                    id=a.id,
                    actor_id=a.actor_id,
                    action=a.action,
                    target=a.target,
                    created_at=a.created_at.isoformat() + "Z",
                )
                for a in rows
            ],
            total=total,
        )
    )


@app.post("/api/v1/samples/import", tags=["samples"], response_model=ApiResponse)
def import_samples(db: DB, user: Analyst):
    """Import packaged samples as ready studies, without inserting fabricated predictions."""
    root = ROOT / "sample-data"
    samples = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    ids = []
    for sample in samples:
        code = sample_names.patient_code(user.id, sample["ecg_id"])
        legacy_code = f"DEMO-{user.id}-{sample['ecg_id']}"
        patient = db.scalar(select(Patient).where(Patient.code.in_((code, legacy_code))))
        if patient is None:
            patient = Patient(
                code=code,
                name="受检者",
                sex="unknown",
                owner_id=user.id,
                note=sample_names.SAMPLE_NOTE,
            )
            db.add(patient)
            db.flush()
            patient.name = sample_names.patient_name(patient.id)
        for kind in ("signal", "image"):
            existing = db.scalar(
                select(Study)
                .where(Study.patient_id == patient.id, Study.kind == kind)
                .limit(1)
            )
            if existing:
                ids.append(existing.id)
                continue
            source = root / sample["directory"]
            if kind == "signal":
                contents = {
                    p.name: p.read_bytes()
                    for p in source.iterdir()
                    if p.suffix in (".hea", ".dat")
                }
                array, metadata = prepare_signal(contents, "filtered_mv")
                image = None
            else:
                contents = {"report.png": (source / "report.png").read_bytes()}
                image, array, metadata = prepare_image(contents)
            key = uuid.uuid4().hex
            folder = cfg.storage_dir / "uploads" / key
            folder.mkdir(parents=True)
            study = Study(
                patient_id=patient.id,
                owner_id=user.id,
                title=sample_names.study_title(kind),
                kind=kind,
                status="ready",
                metadata_json=metadata
                | dict(
                    storage_key=key,
                    files=list(contents),
                    sample_source=sample_names.source_info(sample["ecg_id"]),
                ),
            )
            db.add(study)
            db.flush()
            for name, data in contents.items():
                stored_name = uuid.uuid4().hex + Path(name).suffix
                (folder / stored_name).write_bytes(data)
                db.add(
                    Asset(
                        study_id=study.id,
                        original_name=name,
                        stored_name=stored_name,
                        sha256=hashlib.sha256(data).hexdigest(),
                        byte_size=len(data),
                    )
                )
            np.save(folder / "input.npy", array, allow_pickle=False)
            if image:
                image.thumbnail((1800, 1800))
                image.save(folder / "preview.png")
            ids.append(study.id)
    audit(db, user, "samples.imported", "samples:packaged")
    db.commit()
    return ok(dict(study_ids=ids), "已导入演示样本；分析结果需要实际运行模型生成。")


@app.get("/api/v1/samples/catalog", tags=["samples"])
def sample_catalog(user: Actor):
    rows=json.loads((ROOT/"sample-data/manifest.json").read_text(encoding="utf-8"))
    return ok([dict(id=x["ecg_id"], label=f"PTB-XL #{x['ecg_id']}", files=sorted(p.name for p in (ROOT/"sample-data"/x["directory"]).iterdir() if p.suffix in (".csv",".dat",".hea",".png"))) for x in rows])

@app.get("/api/v1/samples/{sample_id}/files/{filename}", tags=["samples"])
def sample_file(sample_id:int, filename:str, user:Actor):
    rows=json.loads((ROOT/"sample-data/manifest.json").read_text(encoding="utf-8"))
    row=next((x for x in rows if x["ecg_id"]==sample_id),None)
    if not row or filename!=Path(filename).name: raise HTTPException(404,"样例不存在")
    folder=ROOT/"sample-data"/row["directory"]
    allowed={p.name for p in folder.iterdir() if p.suffix in (".csv",".dat",".hea",".png")}
    if filename not in allowed: raise HTTPException(404,"样例不存在")
    return FileResponse(folder/filename,filename=filename)

@app.get("/api/v1/input-template.csv", tags=["samples"])
def csv_template(user:Actor):
    header="time_s,"+",".join(LEADS)+"\n"
    rows="".join(f"{i/100:.2f},"+",".join([""]*12)+"\n" for i in range(1000))
    return Response(("\ufeff"+header+rows).encode("utf-8"),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=ecg-template.csv"})

@app.get("/api/v1/studies/{study_id}/review-neighbors",tags=["reviews"])
def review_neighbors(study_id:int, db:DB, user:Reviewer):
    access_study(db,study_id,user)
    ids=list(db.scalars(select(Study.id).where(Study.status=="awaiting_review").order_by(Study.id)))
    return ok(dict(previous=max((i for i in ids if i<study_id),default=None),next=min((i for i in ids if i>study_id),default=None),remaining=len(ids),position=ids.index(study_id)+1 if study_id in ids else None))

from .agent_lab import router as agent_router
app.include_router(agent_router)

# Built frontend can be served by the same local API process; dev mode uses Vite proxy.
dist = ROOT / "frontend" / "dist"
app.mount(
    "/assets",
    StaticFiles(directory=dist / "assets", check_dir=False),
    name="frontend-assets",
)


@app.get("/{path:path}", include_in_schema=False)
def frontend_page(path: str):
    if path.startswith("api/") or not (dist / "index.html").is_file():
        raise HTTPException(404, "页面或接口不存在；开发模式请先启动Vue前端。")
    return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
