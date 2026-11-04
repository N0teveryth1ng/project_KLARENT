# Agent Reliability Lab

Autonomous QA execution and evaluation platform demonstrating reliable browser testing with failure recovery, idempotency, and crash resilience.

## Overview

Agent Reliability Lab answers: Can an autonomous browser-testing system reliably complete a workflow when the browser, application or network behaves unpredictably?

## Key Features

- **Step-based Execution Engine** - Deterministic scenario execution with Playwright
- **Failure Injection** - Reproducible failure testing
- **Retry & Recovery** - Intelligent failure classification with exponential backoff
- **Idempotency Protection** - Action ledger prevents duplicate side effects
- **Crash Recovery** - Resume interrupted runs from persisted state
- **Evidence Capture** - Screenshots and execution traces
- **Reliability Metrics** - Task success rate, recovery rate from real runs
- **Developer Dashboard** - Web UI for monitoring

## Quick Start

```bash
cp .env.example .env
docker-compose up -d
docker-compose exec app alembic upgrade head
docker-compose exec app python scripts/seed_products.py
docker-compose exec app python scripts/load_scenario.py scenarios/product_purchase.json
```

Access: http://localhost:8000, http://localhost:8000/dashboard/, http://localhost:8000/docs

## Critical Demo: Interrupted Checkout Recovery

Tests idempotency - order created but response lost, system recovers without creating duplicates. The demo app supports idempotent order creation via Idempotency-Key header.

## Testing

```bash
pytest tests/unit -v
```

## Tech Stack

FastAPI, PostgreSQL, Redis, Playwright, SQLAlchemy, Alembic, Pydantic, Jinja2, Docker
