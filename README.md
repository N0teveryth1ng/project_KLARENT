# Agent Reliability Lab

Browser-workflow demo and reliability-testing architecture. It separates successful local browser runs from recovery guarantees that must be demonstrated by dedicated PostgreSQL tests.

## Overview

Agent Reliability Lab is a local browser-workflow testing platform. It runs configured Playwright steps against a demo shopping app and records each run, its step results, action-ledger entries, and screenshots. PostgreSQL is required for the project's recovery lease and fencing features; SQLite is suitable for the local dashboard and standard demo scenario.

## Key Features

- **Step-based Execution Engine** - Runs configured browser actions with Playwright
- **Failure Injection** - Scenario configuration can request reproducible failures; the dashboard does not currently expose these controls
- **Recovery Components** - PostgreSQL recovery lease and fencing components with separate integration tests
- **Idempotency Tracking** - An action ledger tracks execution state; the demo checkout accepts idempotency keys
- **Evidence Capture** - Screenshots and execution traces
- **Execution Metrics** - Counts and rates calculated from saved run records, with recovery-test evidence shown separately
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

Overview highlights the latest run and its passed-step count. The **Runs** page retains both passed and failed attempts, including the failure details when available. An older failed run with no saved exception is identified as historical and is not removed from the success-rate calculation.

## Dashboard Screenshots

These screenshots were captured from the local dashboard. They show the saved local run history at capture time; they are illustrative evidence of the UI and recorded results, not proof of recovery guarantees.

### Overview

![Reliability dashboard overview](artifacts/screenshots/readme/overview.png)

### Scenarios

![Available scenarios and demo setup](artifacts/screenshots/readme/scenarios.png)

### Runs

![Recorded run history](artifacts/screenshots/readme/runs.png)

### Run details

![Recorded browser step results](artifacts/screenshots/readme/run-details.png)

### Evaluation

![Execution evaluation metrics](artifacts/screenshots/readme/evaluation.png)

### Recovery evidence

![Dedicated recovery-test evidence status](artifacts/screenshots/readme/recovery-evidence.png)

## Progress Snapshot (2026-11-06)

- The latest dashboard purchase run passed all **16/16** configured browser steps against the local demo shop.
- The two saved dashboard runs include that success and an earlier failed attempt. The failed attempt stopped before its first step because Playwright raised `NotImplementedError` while launching a subprocess from the Windows web-server event loop. Dashboard runs now launch the browser worker in a separate Python process; the failure remains visible in run history.
- Normal execution success is **1/2 (50%)** for this snapshot. The failed attempt is intentionally included.
- The **16 Action Ledger Side-Effect Records** are ledger rows, not 16 confirmed duplicate orders.
- No dedicated PostgreSQL recovery-test report has been recorded. Worker restart recovery, lost-response checkout recovery, and concurrent-worker fencing remain unverified by this snapshot.

## Understanding Evaluation Metrics

Evaluation metrics are calculated from runs stored in the configured database. A small sample can change the rates significantly; the sample size is shown with the results. The dashboard separates normal browser runs from recovery-configured runs. **Action Ledger Side-Effect Records** counts ledger rows marked as side effects; it is not a count of confirmed duplicate orders. Normal purchase runs do not demonstrate worker restart recovery, lost-response idempotency, or concurrent-worker fencing.

The **Recovery Evidence** page reads a JUnit XML report at `artifacts/logs/recovery-tests.xml`. Without that report, it marks dedicated PostgreSQL recovery tests as **not recorded**, not passed. To create the report, configure `TEST_DATABASE_URL` to a dedicated PostgreSQL database whose name includes `test`, then run:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/agent_reliability_lab_test"
pytest tests/integration/test_lost_response_recovery.py tests/integration/test_checkout_idempotency.py tests/integration/test_concurrent_checkout.py tests/integration/test_recovery_concurrency.py tests/integration/test_execution_manager_fencing_pg.py tests/integration/test_worker_restart_recovery.py --junitxml=artifacts/logs/recovery-tests.xml
```

The worker-restart end-to-end case is skipped unless `RUN_WORKER_RESTART_E2E=1` is set. To run it, start the demo server against the same dedicated test database and set that variable in the pytest shell. These tests clean their PostgreSQL test tables; never point them at development or production data.

## Interrupted Checkout Recovery

The demo checkout endpoint accepts an `Idempotency-Key` header and can simulate a lost response after committing an order with `X-Fail-After-Commit: lost-response`. This supports exercising idempotent checkout behavior through the API or a configured scenario. The dashboard's standard **Product Purchase** run does not inject this failure.

## Testing

```bash
pytest tests/unit -v
```

## Tech Stack

FastAPI, PostgreSQL, Redis, Playwright, SQLAlchemy, Alembic, Pydantic, Jinja2, Docker
