from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.test_run import TestRun
from app.models.scenario import Scenario
from app.evaluation.metrics import MetricsCalculator

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/overview", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    total_runs = db.query(TestRun).count()
    successful = db.query(TestRun).filter(TestRun.status == "PASSED").count()
    failed = db.query(TestRun).filter(TestRun.status == "FAILED").count()
    recovered = db.query(TestRun).filter(TestRun.status == "RECOVERED").count()
    
    calculator = MetricsCalculator(db)
    metrics = calculator.calculate_metrics()
    
    html = f"""
    <html>
    <head><title>Dashboard - Agent Reliability Lab</title>
    <style>body{{font-family:Arial;background:#0d1117;color:#c9d1d9;padding:20px;}}
    .card{{background:#161b22;padding:20px;margin:10px;border:1px solid #30363d;}}
    .stat{{display:inline-block;margin:20px;}}.stat-value{{font-size:32px;color:#58a6ff;}}</style>
    </head>
    <body>
    <h1>Agent Reliability Lab - Dashboard</h1>
    <nav><a href="/dashboard/" style="color:#58a6ff;">Overview</a> | <a href="/dashboard/scenarios" style="color:#58a6ff;">Scenarios</a> | <a href="/dashboard/runs" style="color:#58a6ff;">Runs</a> | <a href="/dashboard/evaluation" style="color:#58a6ff;">Evaluation</a></nav>
    <div class="card">
    <h2>Overview</h2>
    <div class="stat"><div class="stat-value">{total_runs}</div><div>Total Runs</div></div>
    <div class="stat"><div class="stat-value">{successful}</div><div>Successful</div></div>
    <div class="stat"><div class="stat-value">{failed}</div><div>Failed</div></div>
    <div class="stat"><div class="stat-value">{recovered}</div><div>Recovered</div></div>
    </div>
    <div class="card">
    <h2>Metrics</h2>
    <p>Task Success Rate: {metrics['task_success_rate']}%</p>
    <p>Recovery Rate: {metrics['recovery_rate']}%</p>
    <p>Duplicate Side Effects: {metrics['duplicate_side_effect_count']}</p>
    <p>Sample Size: {metrics['sample_size']}</p>
    </div>
    </body></html>
    """
    return HTMLResponse(content=html)
