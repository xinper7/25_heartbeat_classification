import json
from datetime import timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.config import ROOT
from app.db import SessionLocal
from app.inputs import InputError, prepare_signal, read_csv
from app.models import Analysis, JobItem, Study, now
from app.services import recover_stale
from app.worker import run_once

SAMPLE = ROOT / "sample-data/9"


def create_patient(client, headers, name="sample"):
    response = client.post(
        "/api/v1/patients", headers=headers, json=dict(code="P-" + name, name=name)
    )
    assert response.status_code == 201, response.text
    return response.json()["result"]["id"]


def create_study(client, headers, patient_id, kind="signal"):
    response = client.post(
        "/api/v1/studies",
        headers=headers,
        json=dict(patient_id=patient_id, title="test study", kind=kind),
    )
    assert response.status_code == 201, response.text
    return response.json()["result"]["id"]


def upload(client, headers, study_id, kind="signal"):
    names = ["report.png"] if kind == "image" else ["00009_lr.hea", "00009_lr.dat"]
    files = [
        ("files", (name, (SAMPLE / name).read_bytes(), "application/octet-stream"))
        for name in names
    ]
    response = client.post(
        f"/api/v1/studies/{study_id}/assets",
        headers=headers,
        files=files,
        data={"profile": "filtered_mv"},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_login_and_permissions(client, headers):
    assert client.get("/api/v1/patients").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json=dict(username="admin", password="wrong")
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json=dict(username="admin", password="test-password-123!"),
        ).status_code
        == 200
    )
    a = headers("analyst")
    b = headers("other")
    reviewer = headers("reviewer")
    patient = create_patient(client, a)
    study = create_study(client, a, patient)
    assert client.get(f"/api/v1/studies/{study}", headers=b).status_code == 404
    assert client.get("/api/v1/patients", headers=b).json()["result"]["total"] == 0
    assert client.get("/api/v1/users", headers=a).status_code == 403
    assert (
        client.post(
            "/api/v1/patients", headers=reviewer, json=dict(code="x", name="x")
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/studies/{study}", headers=reviewer).status_code == 200


def test_real_signal_analysis_review_and_export(client, headers):
    auth = headers("analyst")
    patient = create_patient(client, auth)
    study = create_study(client, auth, patient)
    assert (
        client.post(f"/api/v1/studies/{study}/analyses", headers=auth).status_code
        == 400
    )
    info = upload(client, auth, study)
    assert info["status"] == "ready"
    preview = client.get(f"/api/v1/studies/{study}/preview", headers=auth).json()[
        "result"
    ]
    assert len(preview["values"]) == 12 and len(preview["values"][0]) == 1000
    response = client.post(f"/api/v1/studies/{study}/analyses", headers=auth)
    assert response.status_code == 201, response.text
    result = response.json()["result"]
    expected = json.loads((ROOT / "sample-data/manifest.json").read_text())[0][
        "expected_signal"
    ]
    np.testing.assert_allclose(
        [p["probability"] for p in result["predictions"]], expected, atol=2e-5
    )
    assert (
        client.post(f"/api/v1/studies/{study}/analyses", headers=auth).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/analyses/{result['id']}/reviews",
            headers=auth,
            json=dict(conclusion="confirmed", comment="review test comment"),
        ).status_code
        == 403
    )
    url = f"/api/v1/analyses/{result['id']}"
    reviewer = headers("reviewer")
    returned = client.post(url + "/reviews", headers=reviewer, json=dict(conclusion="returned", comment="Please clarify input source"))
    assert returned.status_code == 200
    event = returned.json()["result"]["review_history"][0]["id"]
    assert client.get(f"/api/v1/studies/{study}", headers=auth).json()["result"]["status"] == "pending_correction"
    supplement = dict(previous_event_id=event, comment="Confirmed original input source")
    assert client.post(url + "/resubmit", headers=reviewer, json=supplement).status_code == 403
    resubmitted = client.post(url + "/resubmit", headers=auth, json=supplement)
    assert resubmitted.status_code == 200
    assert client.post(url + "/resubmit", headers=auth, json=supplement).status_code == 409
    assert client.post(url + "/reviews", headers=reviewer, json=dict(conclusion="confirmed", comment="stale approval")).status_code == 409
    event = resubmitted.json()["result"]["review_history"][0]["id"]
    response = client.post(
        f"/api/v1/analyses/{result['id']}/reviews",
        headers=headers("reviewer"),
        json=dict(previous_event_id=event, conclusion="confirmed", comment="<script>alert(1)</script> reviewed"),
    )
    assert response.status_code == 200, response.text
    assert (
        client.get(f"/api/v1/studies/{study}", headers=auth).json()["result"]["status"]
        == "archived"
    )
    report = client.get(f"/api/v1/analyses/{result['id']}/report", headers=auth)
    import io
    from pypdf import PdfReader
    assert report.headers['content-type']=='application/pdf'
    reader=PdfReader(io.BytesIO(report.content))
    text=''.join(p.extract_text() for p in reader.pages)
    assert '<script>alert(1)</script> reviewed' in text
    assert len(reader.attachments)==2
    assert len(reader.pages)>=3
    assert (
        "text/csv"
        in client.get("/api/v1/exports/studies.csv", headers=auth).headers[
            "content-type"
        ]
    )
    assert client.delete(f"/api/v1/patients/{patient}", headers=auth).status_code == 409
    response = client.post(
        f"/api/v1/analyses/{result['id']}/reviews",
        headers=headers("reviewer"),
        json=dict(
            conclusion="needs_attention", comment="A second independent review record"
        ),
    )
    assert response.status_code == 409
    history = client.get(f"/api/v1/studies/{study}", headers=auth).json()["result"]["analyses"][0]["review_history"]
    assert [event["conclusion"] for event in history] == ["confirmed", "resubmitted", "returned"]


def test_image_onnx_parity(client, headers):
    auth = headers()
    patient = create_patient(client, auth)
    study = create_study(client, auth, patient, "image")
    upload(client, auth, study, "image")
    assert (
        client.get(f"/api/v1/studies/{study}/preview", headers=auth).headers[
            "content-type"
        ]
        == "image/png"
    )
    r = client.post(f"/api/v1/studies/{study}/analyses", headers=auth)
    assert r.status_code == 201, r.text
    expected = json.loads((ROOT / "sample-data/manifest.json").read_text())[0][
        "expected_image"
    ]
    np.testing.assert_allclose(
        [p["probability"] for p in r.json()["result"]["predictions"]],
        expected,
        atol=2e-5,
    )


def test_bad_files_do_not_advance_study(client, headers):
    auth = headers()
    patient = create_patient(client, auth)
    study = create_study(client, auth, patient)
    bad = client.post(
        f"/api/v1/studies/{study}/assets",
        headers=auth,
        files=[("files", ("../x.csv", b"bad"))],
    )
    assert bad.status_code == 400
    files = [
        ("files", ("00009_lr.hea", (SAMPLE / "00009_lr.hea").read_bytes())),
        ("files", ("00009_lr.dat", bytes(24000))),
    ]
    assert (
        client.post(
            f"/api/v1/studies/{study}/assets", headers=auth, files=files
        ).status_code
        == 400
    )
    assert (
        client.get(f"/api/v1/studies/{study}", headers=auth).json()["result"]["status"]
        == "awaiting_upload"
    )


def test_batch_worker_and_duplicate_prevention(client, headers):
    auth = headers()
    patient = create_patient(client, auth)
    ids = []
    for kind in ("signal", "image"):
        sid = create_study(client, auth, patient, kind)
        upload(client, auth, sid, kind)
        ids.append(sid)
    response = client.post(
        "/api/v1/jobs", headers=auth, json=dict(name="mixed batch", study_ids=ids)
    )
    assert response.status_code == 202, response.text
    jid = response.json()["result"]["id"]
    assert (
        client.post(
            "/api/v1/jobs", headers=auth, json=dict(name="duplicate", study_ids=ids)
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/studies/{ids[0]}/analyses", headers=auth).status_code
        == 409
    )
    assert run_once() is True
    assert run_once() is True
    assert run_once() is False
    result = client.get(f"/api/v1/jobs/{jid}", headers=auth).json()["result"]
    assert result["status"] == "succeeded" and result["counts"]["succeeded"] == 2
    with SessionLocal() as db:
        assert len(db.scalars(select(Analysis)).all()) == 2


def test_expired_lease_recovery_and_failure_retry(client, headers):
    auth = headers()
    patient = create_patient(client, auth)
    sid = create_study(client, auth, patient)
    upload(client, auth, sid)
    jid = client.post(
        "/api/v1/jobs", headers=auth, json=dict(name="interrupted", study_ids=[sid])
    ).json()["result"]["id"]
    with SessionLocal() as db:
        item = db.scalar(select(JobItem))
        item.status = "running"
        item.claim_token = "stale"
        item.attempts = 1
        item.lease_until = now() - timedelta(seconds=5)
        db.get(Study, sid).status = "processing"
        db.commit()
        recover_stale(db)
        assert db.get(JobItem, item.id).status == "queued"
    assert run_once()
    assert (
        client.get(f"/api/v1/jobs/{jid}", headers=auth).json()["result"]["status"]
        == "succeeded"
    )


def test_demo_import_is_idempotent_and_predictions_not_fabricated(client, headers):
    auth = headers()
    a = client.post("/api/v1/samples/import", headers=auth)
    assert a.status_code == 200, a.text
    b = client.post("/api/v1/samples/import", headers=auth)
    assert a.json()["result"]["study_ids"] == b.json()["result"]["study_ids"]
    with SessionLocal() as db:
        assert len(db.scalars(select(Study)).all()) == 10
        assert db.scalar(select(Analysis)) is None
        # Existing installs may retain their original import codes after an upgrade.
        first = db.scalar(select(Study).order_by(Study.id))
        from app.models import Patient

        patient = db.get(Patient, first.patient_id)
        source_id = first.metadata_json["sample_source"]["ecg_id"]
        patient.code = f"DEMO-{patient.owner_id}-{source_id}"
        db.commit()
    legacy = client.post("/api/v1/samples/import", headers=auth)
    assert legacy.status_code == 200
    assert legacy.json()["result"]["study_ids"] == a.json()["result"]["study_ids"]


def test_csv_units_and_column_order():
    x, _ = prepare_signal(
        {
            p.name: p.read_bytes()
            for p in SAMPLE.iterdir()
            if p.suffix in (".hea", ".dat")
        },
        "filtered_mv",
    )
    csv = (SAMPLE / "signal.csv").read_bytes()
    parsed = read_csv(csv, 100, "mV")
    np.testing.assert_allclose(parsed, x, atol=1e-7)
    import csv as c, io

    rows = list(c.reader(io.StringIO(csv.decode())))
    reordered = io.StringIO()
    writer = c.writer(reordered)
    writer.writerow(rows[0][::-1])
    writer.writerows([[float(s) * 1000 for s in row[::-1]] for row in rows[1:]])
    np.testing.assert_allclose(
        read_csv(reordered.getvalue().encode(), 100, "uV"), x, atol=1e-7
    )
    import pytest

    with pytest.raises(InputError):
        read_csv(csv, 500, "mV")
    with pytest.raises(InputError):
        read_csv(b"I,II\nNaN,1", 100, "mV")


def test_account_management_and_date_filters(client, headers):
    admin = headers()
    r = client.post(
        "/api/v1/users",
        headers=admin,
        json=dict(
            username="new_staff",
            name="Staff",
            password="new-password-123!",
            role="analyst",
        ),
    )
    assert r.status_code == 201, r.text
    uid = r.json()["result"]["id"]
    assert (
        client.patch(
            f"/api/v1/users/{uid}", headers=admin, json=dict(role="reviewer")
        ).json()["result"]["role"]
        == "reviewer"
    )
    assert (
        client.patch(
            "/api/v1/users/1", headers=admin, json=dict(active=False)
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=admin,
            json=dict(current_password="wrong", new_password="another-password-123!"),
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=admin,
            json=dict(
                current_password="test-password-123!",
                new_password="another-password-123!",
            ),
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json=dict(username="admin", password="another-password-123!"),
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me", headers=admin).status_code == 401
    admin = {"Authorization": "Bearer " + login.json()["result"]["access_token"]}
    pid = create_patient(client, admin)
    create_study(client, admin, pid)
    assert (
        client.get(
            "/api/v1/studies?date_from=2099-01-01T00:00:00", headers=admin
        ).json()["result"]["total"]
        == 0
    )
    assert (
        client.get("/api/v1/studies?date_to=2000-01-01T00:00:00", headers=admin).json()[
            "result"
        ]["total"]
        == 0
    )
    assert (
        client.get("/api/v1/studies?date_from=not-a-date", headers=admin).status_code
        == 422
    )
