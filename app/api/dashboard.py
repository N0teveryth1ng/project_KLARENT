from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.test_run import TestRun
from app.models.action_ledger import ActionLedger
from app.evaluation.metrics import MetricsCalculator

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
@router.get("/overview", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    # Summary metrics
    total_runs = db.query(TestRun).count()
    successful = db.query(TestRun).filter(TestRun.status == "PASSED").count()
    failed = db.query(TestRun).filter(TestRun.status == "FAILED").count()
    recovered = db.query(TestRun).filter(TestRun.status == "RECOVERED").count()

    # Overall metrics
    calculator = MetricsCalculator(db)
    metrics = calculator.calculate_metrics()

    # Recent runs (last 5)
    recent_runs = (
        db.query(TestRun)
        .order_by(TestRun.started_at.desc())
        .limit(5)
        .all()
    )

    # Duplicate side effects for recent runs
    recent_duplicate_count = (
        db.query(ActionLedger)
        .filter(
            ActionLedger.run_id.in_([r.id for r in recent_runs]),
            ActionLedger.side_effect_occurred == True,
        )
        .count()
    )

    # Build recent runs HTML fragment
    if recent_runs:
        rows = []
        for r in recent_runs:
            duration = (
                (r.completed_at - r.started_at).total_seconds()
                if r.started_at and r.completed_at
                else "N/A"
            )
            rows.append(
                f"<tr><td>{r.id}</td><td>{r.status}</td><td>{r.scenario.name if r.scenario else 'N/A'}</td>"
                f"<td>{r.started_at}</td><td>{r.completed_at}</td><td>{duration}</td>"
                f"<td><a href='/dashboard/run/{r.id}'>View</a></td></tr>"
            )
        recent_table = (
            "<table><thead><tr><th>ID</th><th>Status</th><th>Scenario</th><th>Started</th>"
            "<th>Completed</th><th>Duration (s)</th><th>Details</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    else:
        recent_table = "<p>No test runs available.</p>"

    # Full HTML page
    html = f"""
    <html>
    <head>
    <title>Dashboard - Agent Reliability Lab</title>
    <style>
    body{{font-family:Arial;background:#0d1117;color:#c9d1d9;padding:20px;}}
    .card{{background:#161b22;padding:20px;margin:10px;border:1px solid #30363d;}}
    .stat{{display:inline-block;margin:20px;}}
    .stat-value{{font-size:32px;color:#58a6ff;}}
    table{{width:100%;border-collapse:collapse;margin-top:10px;}}
    th, td{{padding:8px;border:1px solid #30363d;text-align:left;}}
    a{{color:#58a6ff;text-decoration:none;}}
    </style>
    </head>
    <body>
    <h1>Agent Reliability Lab - Dashboard</h1>
    <nav>
        <a href="/dashboard/" style="color:#58a6ff;">Overview</a> |
        <a href="/dashboard/scenarios" style="color:#58a6ff;">Scenarios</a> |
        <a href="/dashboard/runs" style="color:#58a6ff;">Runs</a> |
        <a href="/dashboard/evaluation" style="color:#58a6ff;">Evaluation</a>
    </nav>
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
        <p>Duplicate Side Effects (recent runs): {recent_duplicate_count}</p>
        <p>Sample Size: {metrics['sample_size']}</p>
    </div>
    <div class="card">
        <h2>Recent Test Runs</h2>
        {recent_table}
    </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
