import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.evaluation.metrics import MetricsCalculator
from app.models.scenario import Scenario
from app.models.step_execution import StepExecution
from app.models.test_run import TestRun
from demo_app.models import Product, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _execute_run(run_id: str) -> None:
    """Run Playwright in a fresh process with Windows' subprocess-capable loop."""
    project_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-m", "scripts.run_single", run_id],
        cwd=project_root,
        check=False,
    )


@router.get("/", response_class=HTMLResponse)
@router.get("/overview", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    runs = db.query(TestRun).order_by(TestRun.created_at.desc()).limit(10).all()
    metrics = MetricsCalculator(db).calculate_metrics()
    return templates.TemplateResponse(
        request=request,
        name="dashboard/overview.html",
        context={
            "total_runs": db.query(TestRun).count(),
            "successful": db.query(TestRun).filter(TestRun.status == "PASSED").count(),
            "failed": db.query(TestRun).filter(TestRun.status == "FAILED").count(),
            "recovered": db.query(TestRun).filter(TestRun.status == "RECOVERED").count(),
            "metrics": metrics,
            "recent_runs": runs,
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
    runs = db.query(TestRun).order_by(TestRun.created_at.desc()).all()
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
    return templates.TemplateResponse(
        request=request,
        name="dashboard/run_detail.html",
        context={"run": run, "steps": steps},
    )


@router.get("/evaluation", response_class=HTMLResponse)
def evaluation_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="dashboard/evaluation.html",
        context={"metrics": MetricsCalculator(db).calculate_metrics()},
    )


@router.get("/failure-lab", response_class=HTMLResponse)
def failure_lab_page(request: Request, db: Session = Depends(get_db)):
    scenarios = db.query(Scenario).order_by(Scenario.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard/failure_lab.html",
        context={"scenarios": scenarios},
    )
