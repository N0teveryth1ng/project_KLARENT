# Agent Reliability Lab

Autonomous QA execution and evaluation platform demonstrating reliable browser testing with failure recovery, idempotency, and crash resilience.

## Overview

Agent Reliability Lab is a local browser-workflow testing platform. It runs configured Playwright steps against a demo shopping app and records each run, its step results, action-ledger entries, and screenshots. PostgreSQL is required for the project's recovery lease and fencing features; SQLite is suitable for the local dashboard and standard demo scenario.

## Key Features

- **Step-based Execution Engine** - Runs configured browser actions with Playwright
- **Failure Injection** - Scenario configuration can request reproducible failures; the dashboard does not currently expose these controls
- **Retry & Recovery Components** - Retry classification/backoff and PostgreSQL recovery lease/fencing components
- **Idempotency Tracking** - An action ledger tracks execution state; the demo checkout accepts idempotency keys
- **Evidence Capture** - Screenshots and execution records
- **Evidence Capture** - Screenshots and execution traces
- **Reliability Metrics** - Task success rate, recovery rate from real runs
- **Developer Dashboard** - Web UI for monitoring

## Quick Start with Docker

Copy the sample environment file, then start the app and its PostgreSQL and Redis services.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed_products.py
```

Open http://localhost:8000 or the dashboard at http://localhost:8000/dashboard/.

## Quick Start with Local SQLite

If the Python dependencies and Playwright Chromium are already installed, run the app from the project directory in PowerShell:

```powershell
$env:DATABASE_URL = "sqlite:///./test.db"
$env:DEBUG = "false"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app creates any missing SQLite tables at startup. To install dependencies and the browser in a new environment, run:

```powershell
python -m pip install -e .
python -m playwright install chromium
```

Use `http://localhost:8000` in the browser. The `0.0.0.0` address is the server bind address; it is not part of the browser URL.

## Run a demo test from the dashboard

1. Start the app and open http://localhost:8000/dashboard/scenarios.
2. Select **Prepare demo scenario**. This safely adds the included scenario, sample laptop, and `testuser` demo login to the configured database. Repeating this setup does not add another copy of these records.
3. Select **Run** beside **Product Purchase**. The app starts a headless Playwright browser and directs it to the local demo shop at http://localhost:8000/demo/products.
4. The browser logs in, searches for a laptop, adds it to the cart, and submits checkout. The run details page refreshes while the test is running.
5. Review the final run status and each step on the run details page. Use **Runs** to find previous attempts and **Overview** or **Evaluation** to see aggregate results.

The included scenario runs only against this project's local demo shop; it does not contact an external store. A **PASSED** run means all configured browser actions completed. The sample scenario currently records the checkout response but does not independently assert every resulting order field.

## Understanding Evaluation Metrics

Evaluation metrics are calculated from the runs stored in the configured database. A small sample can change the rates significantly; the sample size is shown with the results. The current **Duplicate Side Effects** value counts action-ledger records marked as side effects. It is not a count of confirmed duplicate orders. The dashboard's **Failure Lab** page is informational; failure injection is not currently available through its controls.

## Interrupted Checkout Recovery

The demo checkout endpoint accepts an `Idempotency-Key` header and can simulate a lost response after committing an order with `X-Fail-After-Commit: lost-response`. This supports exercising idempotent checkout behavior through the API or a configured scenario. The dashboard's standard **Product Purchase** run does not inject this failure.

## Testing

```bash
pytest tests/unit -v
```

## Tech Stack

FastAPI, PostgreSQL, Redis, Playwright, SQLAlchemy, Alembic, Pydantic, Jinja2, Docker
