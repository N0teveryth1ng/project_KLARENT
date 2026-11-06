import hashlib
import json
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.evaluation.metrics import MetricsCalculator
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.test_run import TestRun
from demo_app.models import Product, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

RECOVERY_TESTS = [
    {
        "area": "Worker restart recovery",
        "case": "test_worker_process_restart_recovers_interrupted_checkout_postgres",
        "source": "test_worker_restart_recovery.py",
        "note": "Opt-in end-to-end test; requires RUN_WORKER_RESTART_E2E=1 and a running demo server.",
    },
    {
        "area": "Lost checkout response",
        "case": "test_checkout_commits_response_lost_recovery_finds_original_order",
        "source": "test_lost_response_recovery.py",
        "note": "Checks that a committed order is found after the response is lost and a retry does not duplicate it.",
    },
    {
        "area": "Concurrent checkout idempotency",
        "case": "test_concurrent_duplicate_checkout_creates_one_order",
        "source": "test_concurrent_checkout.py",
        "note": "Checks duplicate concurrent checkouts using the same idempotency key.",
    },
    {
        "area": "Single-order idempotency",
        "case": "test_same_idempotency_key_creates_only_one_order",
        "source": "test_checkout_idempotency.py",
        "note": "Checks that retrying checkout with the same key returns the original order.",
    },
    {
        "area": "Concurrent lease ownership",
        "case": "test_two_workers_cannot_acquire_same_active_lease_postgres",
        "source": "test_recovery_concurrency.py",
        "note": "Checks that only one concurrent worker acquires an active run lease.",
    },
    {
        "area": "Crashed-worker lease recovery",
        "case": "test_crashed_worker_lease_expires_and_reclaimed_postgres",
        "source": "test_recovery_concurrency.py",
        "note": "Checks that a new worker can reclaim an expired lease.",
    },
    {
        "area": "Old-worker fencing",
        "case": "test_old_worker_cannot_renew_or_release_new_lease_postgres",
        "source": "test_recovery_concurrency.py",
        "note": "Checks that the previous lease owner cannot alter a reclaimed lease.",
    },
    {
        "area": "Execution fencing",
        "case": "test_actual_execute_run_stops_when_ownership_lost_postgres",
        "source": "test_execution_manager_fencing_pg.py",
        "note": "Checks that a run stops after its worker loses lease ownership.",
    },
]


def _execute_run(run_id: str) -> None:
    """Run Playwright in a fresh process with Windows' subprocess-capable loop."""
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_single", run_id],
        cwd=project_root,
        check=False,
    )
    if result.returncode:
        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == uuid.UUID(run_id)).first()
            if run and run.status in {"QUEUED", "RUNNING"}:
                run.status = "FAILED"
                run.completed_at = datetime.utcnow()
                run.run_metadata = {
                    **(run.run_metadata or {}),
                    "failure": {
                        "phase": "worker_process",
                        "error_type": "WorkerProcessError",
                        "message": f"Browser worker exited with code {result.returncode} before recording a result.",
                    },
                }
                db.commit()
        finally:
            db.close()


def _step_counts(run: TestRun) -> tuple[int, int]:
    steps = run.step_executions
    expected = run.total_steps or len((run.scenario.configuration or {}).get("steps", []))
    passed = sum(step.status == "PASSED" for step in steps)
    return passed, expected


def _failure_summary(run: TestRun) -> str:
    metadata = run.run_metadata or {}
    failure = metadata.get("failure") or {}
    if failure:
        message = failure.get("message") or "No exception message was captured."
        return f"{failure.get('error_type', 'Run error')}: {message}"

    failed_step = next((step for step in run.step_executions if step.status in {"FAILED", "INTERRUPTED"}), None)
    if failed_step:
        return failed_step.error_message or f"{failed_step.status} at {failed_step.step_id}"
    if run.status == "FAILED" and not run.step_executions:
        return "Failed before the first step; this historical run did not store its exception."
    if run.status == "FAILED":
        return "Run failed; no error detail was stored."
    return ""


def _recovery_test_evidence() -> dict:
    project_root = Path(__file__).resolve().parents[2]
    report_path = project_root / "artifacts" / "logs" / "recovery-tests.xml"
    if not report_path.exists():
        return {"report_found": False, "report_path": str(report_path), "tests": RECOVERY_TESTS}

    try:
        root = ET.parse(report_path).getroot()
        cases = root.findall(".//testcase")
        by_name = {case.get("name", ""): case for case in cases}
        results = []
        for expected in RECOVERY_TESTS:
            case = by_name.get(expected["case"])
            result = "NOT IN REPORT"
            duration = None
            if case is not None:
                duration = case.get("time")
                if case.find("failure") is not None or case.find("error") is not None:
                    result = "FAILED"
                elif case.find("skipped") is not None:
                    result = "SKIPPED"
                else:
                    result = "PASSED"
            results.append({**expected, "result": result, "duration": duration})
        return {"report_found": True, "report_path": str(report_path), "tests": results}
    except (ET.ParseError, OSError):
        return {"report_found": False, "report_path": str(report_path), "invalid_report": True, "tests": RECOVERY_TESTS}


def _dashboard_summary(db: Session) -> dict:
    runs = (
        db.query(TestRun)
        .options(joinedload(TestRun.scenario))
        .order_by(TestRun.created_at.desc())
        .all()
    )
    metrics = MetricsCalculator(db).calculate_metrics()
    for run in runs:
        run.passed_steps, run.expected_steps = _step_counts(run)
        run.failure_summary = _failure_summary(run)

    completed_statuses = {"PASSED", "FAILED"}
    normal_runs = [
        run for run in runs
        if not (run.scenario and (run.scenario.configuration or {}).get("failure_injection"))
        and run.status in completed_statuses
    ]
    recovery_runs = [
        run for run in runs
        if run.status == "RECOVERED"
        or (run.scenario and (run.scenario.configuration or {}).get("failure_injection"))
    ]
    latest = runs[0] if runs else None
    return {
        "runs": runs,
        "latest_run": latest,
        "normal_runs": normal_runs,
        "normal_passed": sum(run.status == "PASSED" for run in normal_runs),
        "normal_completed": len(normal_runs),
        "recovery_runs": recovery_runs,
        "recovery_passed": sum(run.status in {"PASSED", "RECOVERED"} for run in recovery_runs),
        "recovery_failed": sum(run.status == "FAILED" for run in recovery_runs),
        "metrics": metrics,
        "action_ledger_side_effect_records": metrics.get("duplicate_side_effect_count", 0),
        "recovery_test_evidence": _recovery_test_evidence(),
    }


@router.get("/", response_class=HTMLResponse)
@router.get("/overview", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    summary = _dashboard_summary(db)
    runs = summary["runs"]
    return templates.TemplateResponse(
        request=request,
        name="dashboard/overview.html",
        context={
            **summary,
            "total_runs": len(runs),
            "successful": sum(run.status == "PASSED" for run in runs),
            "failed": sum(run.status == "FAILED" for run in runs),
            "recovered": sum(run.status == "RECOVERED" for run in runs),
            "recent_runs": runs[:10],
        },
    )


@router.get("/scenarios", response_class=HTMLResponse)
def scenarios_page(request: Request, db: Session = Depends(get_db)):
    scenarios = db.query(Scenario).order_by(Scenario.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard/scenarios.html",
        context={"scenarios": scenarios, "ready": request.query_params.get("ready") == "1"},
    )


@router.post("/scenarios/prepare-demo")
def prepare_demo(db: Session = Depends(get_db)):
    """Add the included purchase scenario and its local demo shop data."""
    project_root = Path(__file__).resolve().parents[2]
    scenario_data = json.loads((project_root / "scenarios" / "product_purchase.json").read_text(encoding="utf-8"))

    demo_user = db.query(User).filter(User.username == "testuser").first()
    if not demo_user:
        db.add(User(
            username="testuser",
            email="testuser@example.test",
            password_hash=hashlib.sha256(b"testpass").hexdigest(),
        ))

    if not db.query(Product).filter(Product.name == "Laptop").first():
        db.add(Product(name="Laptop", description="High performance laptop", price=999.99, stock=10))

    scenario = db.query(Scenario).filter(Scenario.name == scenario_data["name"]).first()
    if not scenario:
        db.add(Scenario(
            name=scenario_data["name"],
            description=scenario_data.get("description"),
            configuration=scenario_data,
        ))

    db.commit()
    return RedirectResponse(url="/dashboard/scenarios?ready=1", status_code=303)


@router.post("/scenarios/{scenario_id}/run")
def start_run(scenario_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        scenario_uuid = uuid.UUID(scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Scenario not found") from exc

    scenario = db.query(Scenario).filter(Scenario.id == scenario_uuid).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    run = TestRun(scenario_id=scenario.id, status="QUEUED", environment="local")
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_execute_run, str(run.id))
    return RedirectResponse(url=f"/dashboard/runs/{run.id}", status_code=303)


@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, db: Session = Depends(get_db)):
    runs = _dashboard_summary(db)["runs"]
    return templates.TemplateResponse(request=request, name="dashboard/runs.html", context={"runs": runs})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
@router.get("/run/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str, db: Session = Depends(get_db)):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    run = db.query(TestRun).filter(TestRun.id == run_uuid).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = db.query(StepExecution).filter(StepExecution.run_id == run.id).order_by(StepExecution.started_at.asc()).all()
    run.passed_steps, run.expected_steps = _step_counts(run)
    run.failure_summary = _failure_summary(run)
    return templates.TemplateResponse(
        request=request,
        name="dashboard/run_detail.html",
        context={"run": run, "steps": steps},
    )


@router.get("/evaluation", response_class=HTMLResponse)
def evaluation_page(request: Request, db: Session = Depends(get_db)):
    summary = _dashboard_summary(db)
    return templates.TemplateResponse(
        request=request,
        name="dashboard/evaluation.html",
        context=summary,
    )


@router.get("/recovery-evidence", response_class=HTMLResponse)
@router.get("/failure-lab", response_class=HTMLResponse)
def recovery_evidence_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="dashboard/recovery_evidence.html",
        context={"recovery_test_evidence": _recovery_test_evidence()},
    )
