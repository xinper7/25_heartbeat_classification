"""Exercise the running local MySQL application with real model inference and browser UI.

Creates explicitly named acceptance records. Does not delete existing business records.
"""

import concurrent.futures
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings

BASE = "http://127.0.0.1:8000"
cfg = get_settings()
OUT = ROOT / "runtime/qa"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "verification.json"
SAMPLE = ROOT / "sample-data/9"


def checked(response, expected=(200, 201, 202)):
    if response.status_code not in expected:
        message = (
            response.json().get("msg")
            if response.headers.get("content-type", "").startswith("application/json")
            else "non-JSON response"
        )
        raise AssertionError(f"HTTP {response.status_code}: {message}")
    return response.json()["result"]


def make_study(client, patient_id, kind, label):
    sid = checked(
        client.post(
            "/api/v1/studies", json=dict(patient_id=patient_id, title=label, kind=kind)
        )
    )["id"]
    names = ["report.png"] if kind == "image" else ["00009_lr.hea", "00009_lr.dat"]
    files = [
        ("files", (n, (SAMPLE / n).read_bytes(), "application/octet-stream"))
        for n in names
    ]
    checked(
        client.post(
            f"/api/v1/studies/{sid}/assets",
            files=files,
            data={"profile": "filtered_mv"},
        )
    )
    return sid


def summary(values):
    return dict(
        count=len(values),
        mean_ms=round(statistics.mean(values), 3),
        p95_ms=round(float(np.percentile(values, 95)), 3),
        max_ms=round(max(values), 3),
        min_ms=round(min(values), 3),
    )


def browser_flow(playwright, name, engine, credentials):
    started = time.perf_counter()
    browser = None
    record = dict(browser=name, passed=False, steps=[], display_ms={}, errors=[])
    try:
        if name == "Chrome":
            browser = engine.launch(channel="chrome", headless=True)
        else:
            browser = engine.launch(headless=True)
        record["version"] = browser.version
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
            timezone_id="Asia/Shanghai",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: record["errors"].append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        page.screenshot(path=str(OUT / f"{name.lower()}-login.png"), full_page=True)
        page.get_by_test_id("login-username").fill(credentials[0])
        page.get_by_test_id("login-password").fill(credentials[1])
        page.get_by_test_id("login-submit").click()
        page.locator(".page-heading h1").filter(has_text="工作概览").wait_for()
        page.locator(".content > .el-loading-mask").wait_for(state="hidden")
        record["steps"].append("登录和工作概览")
        page.screenshot(path=str(OUT / f"{name.lower()}-dashboard.png"), full_page=True)
        for kind, label in [("signal", "数字信号分析"), ("image", "报告图分析")]:
            page.get_by_role("navigation").get_by_role(
                "button", name=label, exact=True
            ).click()
            page.locator(".content > .el-loading-mask").wait_for(state="hidden")
            page.get_by_test_id("workspace-patient").click()
            page.get_by_role("option").first.click()
            page.get_by_test_id("workspace-title").fill(f"浏览器验收 · {name} · {kind}")
            names = (
                ["report.png"] if kind == "image" else ["00009_lr.hea", "00009_lr.dat"]
            )
            page.get_by_test_id("workspace-files").set_input_files(
                [str(SAMPLE / n) for n in names]
            )
            page.get_by_test_id("upload-submit").click()
            page.locator(".validation-success").wait_for()
            page.evaluate(
                "window.__ecgTiming = 0; window.addEventListener('ecg-analysis-rendered',e=>window.__ecgTiming=e.detail.displayMs)"
            )
            page.get_by_test_id("analyze-submit").click()
            page.wait_for_function("window.__ecgTiming > 0", timeout=30000)
            assert page.locator(".prediction").count() == 5
            record["display_ms"][kind] = round(page.evaluate("window.__ecgTiming"), 3)
            record["steps"].append(kind + " 上传/校验/预览/真实推理/展示")
            page.screenshot(
                path=str(OUT / f"{name.lower()}-{kind}.png"), full_page=True
            )
            with page.expect_download() as download:
                page.get_by_role("button", name="导出报告", exact=True).click()
            downloaded = download.value
            report_path = OUT / f"{name.lower()}-{kind}-report.html"
            downloaded.save_as(str(report_path))
            assert "心电分析报告" in report_path.read_text(encoding="utf-8")
            page.get_by_role("button", name="填写复核意见", exact=True).click()
            page.get_by_test_id("review-comment").fill(
                "自动化功能验证：确认意见保存、归档和导出流程。本条为演示数据。"
            )
            page.get_by_test_id("review-submit").click()
            page.locator(".el-dialog:visible").wait_for(state="hidden")
            page.locator(".review-note").wait_for()
            record["steps"].append(kind + " 报告导出和复核归档")
        for route, title in [
            ("patients", "受检者档案"),
            ("studies", "检查记录"),
            ("review", "复核中心"),
            ("jobs", "批量任务"),
            ("models", "模型与状态"),
            ("admin", "系统管理"),
        ]:
            page.get_by_role("navigation").get_by_role(
                "button", name=title, exact=True
            ).click()
            page.locator(".page-heading h1").wait_for()
            page.locator(".content > .el-loading-mask").wait_for(state="hidden")
            record["steps"].append("页面导航 " + route)
        page.get_by_role("navigation").get_by_role(
            "button", name="工作概览", exact=True
        ).click()
        page.locator(".content > .el-loading-mask").wait_for(state="hidden")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "mobile viewport overflow"
        page.screenshot(path=str(OUT / f"{name.lower()}-mobile.png"), full_page=True)
        page.get_by_role("button", name="打开导航").click()
        page.get_by_role("navigation").get_by_role(
            "button", name="检查记录", exact=True
        ).click()
        record["steps"].append("390px移动视口和导航")
        assert not record["errors"], record["errors"]
        record["passed"] = True
    except Exception as exc:
        record["failure"] = str(exc)[:1800]
        if browser:
            try:
                page.screenshot(
                    path=str(OUT / f"{name.lower()}-failure.png"), full_page=True
                )
            except Exception:
                pass
    finally:
        if browser:
            browser.close()
    record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    return record


def verify_browsers(report):
    report["browsers"] = []
    report["browser_verified_at"] = datetime.now(timezone.utc).isoformat()
    with sync_playwright() as playwright:
        for name, engine in [
            ("Chrome", playwright.chromium),
            ("Firefox", playwright.firefox),
            ("WebKit", playwright.webkit),
        ]:
            result = browser_flow(
                playwright,
                name,
                engine,
                (cfg.bootstrap_admin_username, cfg.bootstrap_admin_password),
            )
            report["browsers"].append(result)
            print(
                name,
                "PASS" if result["passed"] else "FAIL",
                result.get("display_ms"),
                flush=True,
            )
    report["passed"] = all(r["passed"] for r in report["browsers"])
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Verification saved:", REPORT)
    if not report["passed"]:
        for row in report["browsers"]:
            if not row["passed"]:
                print(row["browser"], row.get("failure"))
        raise SystemExit(1)


def main():
    if "--browser-only" in sys.argv:
        verify_browsers(json.loads(REPORT.read_text(encoding="utf-8")))
        return
    report = dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        python=sys.version.split()[0],
        platform=platform.platform(),
        threads=cfg.model_threads,
        database="MySQL",
        model_parity=[],
        http_performance={},
        browsers=[],
        safari=dict(
            status="pending", reason="真实Safari设备尚未测试；WebKit不替代Safari。"
        ),
    )
    with httpx.Client(base_url=BASE, timeout=45, trust_env=False) as client:
        health = checked(client.get("/api/v1/health"))
        assert health["ready"]
        login = checked(
            client.post(
                "/api/v1/auth/login",
                json=dict(
                    username=cfg.bootstrap_admin_username,
                    password=cfg.bootstrap_admin_password,
                ),
            )
        )
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        imported = checked(client.post("/api/v1/samples/import"))
        report["sample_studies"] = imported["study_ids"]
        patient_id = checked(client.get("/api/v1/patients", params={"page_size": 100}))[
            "items"
        ][0]["id"]
        manifest = json.loads((ROOT / "sample-data/manifest.json").read_text())
        from app.inference import get_engine
        from app.inputs import prepare_signal, prepare_image

        model_engine = get_engine()
        model_engine.warmup()
        for sample in manifest:
            folder = ROOT / "sample-data" / sample["directory"]
            signal, _ = prepare_signal(
                {
                    p.name: p.read_bytes()
                    for p in folder.iterdir()
                    if p.suffix in (".hea", ".dat")
                },
                "filtered_mv",
            )
            image = prepare_image({"report.png": (folder / "report.png").read_bytes()})[
                1
            ]
            for kind, array in [("signal", signal), ("image", image)]:
                result = model_engine.predict(kind, array)
                expected = sample["expected_" + kind]
                differences = [
                    abs(p["probability"] - e)
                    for p, e in zip(result["predictions"], expected)
                ]
                changed = sum(
                    p["positive"] != (e >= p["threshold"])
                    for p, e in zip(result["predictions"], expected)
                )
                assert max(differences) < 2e-5 and changed == 0
                report["model_parity"].append(
                    dict(
                        ecg_id=sample["ecg_id"],
                        kind=kind,
                        max_absolute_difference=max(differences),
                        changed_decisions=changed,
                    )
                )
        for kind in ("signal", "image"):
            timings = []
            inference = []
            for i in range(30):
                sid = make_study(
                    client, patient_id, kind, f"性能验收 · {kind} · {i + 1:02d}"
                )
                t = time.perf_counter()
                result = checked(client.post(f"/api/v1/studies/{sid}/analyses"))
                timings.append((time.perf_counter() - t) * 1000)
                inference.append(result["timings"]["inference_ms"])
            report["http_performance"][kind] = dict(
                http=summary(timings),
                inference=summary(inference),
                scope="单条、已上传校验、预热模型；HTTP计时包含服务及数据库往返，不含上传和页面渲染",
            )
        ids = [
            make_study(client, patient_id, kind, "批量验收 · " + kind)
            for kind in ("signal", "image")
        ]
        job = checked(
            client.post(
                "/api/v1/jobs", json=dict(name="混合批次 · MySQL验收", study_ids=ids)
            )
        )
        for _ in range(60):
            job = checked(client.get(f"/api/v1/jobs/{job['id']}"))
            if job["status"] in ("succeeded", "failed", "partial"):
                break
            time.sleep(0.5)
        assert job["status"] == "succeeded", job
        from app.db import SessionLocal
        from app.models import Analysis
        from sqlalchemy import select, func

        with SessionLocal() as db:
            counts = dict(
                db.execute(
                    select(Analysis.study_id, func.count())
                    .where(Analysis.study_id.in_(ids))
                    .group_by(Analysis.study_id)
                ).all()
            )
        assert all(counts.get(sid) == 1 for sid in ids)
        report["batch"] = dict(
            passed=True, total=2, unique_result_per_study=True, status=job["status"]
        )
    verify_browsers(report)


if __name__ == "__main__":
    main()
