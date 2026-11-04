# Phase 0: Research & Architecture

**Status:** Complete - Awaiting Review  
**Date:** 2025-10-15  

---

## 1. Klarent Product Context (Public Research)

From public sources (klarent.ai):
- **Product:** Klarent (formerly ForeAI) - Autonomous QA platform for web, iOS, Android
- **Approach:** Multi-agent system (Explorer, Planner, Coder, Verifier, Runner, Notifier) that generates, executes, and maintains tests
- **Key Features:** Plain-English test creation, self-healing tests, cross-browser/device execution, CI/CD integration
- **Focus:** Reducing test maintenance burden through AI agents that adapt to UI changes

**Engineering Problems (Publicly Observable):**
1. **Test maintenance/flakiness** - Tests break when UI changes; need self-healing
2. **Test generation** - Converting requirements into executable tests
3. **Execution reliability** - Tests need to run reliably across environments
4. **Scale** - Parallel execution, coverage management

Our demo (Agent Reliability Lab) takes a different angle - focusing on the **execution/reliability infrastructure**: failure handling, recovery, idempotency, crash recovery, state persistence. This complements Klarent's approach without reproducing internals.

---

## 2. Core Engineering Problems to Solve

Based on the plan, the demo must answer: **"Can an autonomous browser-testing system reliably complete a workflow when the browser, application or network behaves unpredictably?"**

Key problems:
1. **Non-deterministic execution** - Network timeouts, browser crashes, slow responses
2. **Lost responses after side effects** - Critical: order submitted successfully but response lost → retry could duplicate
3. **Crash recovery** - Worker dies mid-execution, must resume from persisted state without repeating completed side effects
4. **Failure classification** - Distinguish retryable (network timeout) from non-retryable (bad credentials, business validation failure)
5. **Idempotency** - Prevent duplicate business operations even with retries
6. **State consistency** - Track execution state precisely across steps, retries, recoveries
7. **Trustworthy results** - Evidence-based assertions, not just "no exception"

---

## 3. Proposed System Architecture

### High-Level Architecture (Modular Monolith)
```
Dashboard (Jinja2/HTML/JS)
    ↓
FastAPI Application
    ↓
Test Run Manager
    ↓
Execution Engine
    ├── Scenario Planner
    ├── Playwright Browser Controller
    ├── Step Executor
    ├── Assertion Engine
    ├── Retry and Recovery Manager
    ├── Idempotency Manager
    └── Failure Injection
    ↓
Execution State Manager
    ├── PostgreSQL (durable source of truth)
    └── Redis (coordination/locks/short-lived)
    ↓
Evidence and Evaluation Engine
    ↓
Results Dashboard
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Test Run Manager** | Creates runs, manages lifecycle, coordinates workers |
| **Scenario Planner** | Loads and validates scenario definitions |
| **Playwright Browser Controller** | Manages browser instances, enforces navigation restrictions |
| **Step Executor** | Executes individual steps with verification |
| **Assertion Engine** | Validates postconditions, checks app state |
| **Retry and Recovery Manager** | Classifies failures, applies retry policy, orchestrates recovery |
| **Idempotency Manager** | Manages action ledger, prevents duplicate side effects |
| **Failure Injection** | Deterministic failure injection for testing |
| **Execution State Manager** | Persists state to PostgreSQL, coordinates via Redis |
| **Evidence and Evaluation Engine** | Captures screenshots/logs, computes reliability metrics |

### Technology Stack
| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.12+ | Rich async support, good ecosystem |
| Backend | FastAPI | Modern, async, great OpenAPI/docs |
| Browser Automation | Playwright | Reliable, cross-browser, good control |
| Database | PostgreSQL | ACID, transactions, durable state |
| Cache/Coordination | Redis | Locks, short-lived state (optional for history) |
| ORM | SQLAlchemy 2.0 | Mature, flexible |
| Migrations | Alembic | Standard for SQLAlchemy |
| Validation | Pydantic v2 | Type safety, validation |
| Frontend | Jinja2 + HTML/CSS/JS | Simple, server-rendered (as specified) |
| Testing | pytest | Standard |
| Infrastructure | Docker Compose | Easy local setup |

---

## 4. Failure Modes & Classification

### Failure Categories

**A. Browser Failures (Retryable in some cases)**
- Browser process termination → Retryable if recoverable
- Page crash → Retryable with fresh page/browser
- Navigation timeout → Retryable with backoff
- Element not found → May be retryable if transient (stale state), or non-retryable if logic error
- Stale element / changed page state → Often retryable

**B. Network Failures (Mostly Retryable)**
- Temporary request timeout → Retryable
- HTTP 500 response → Retryable (server error)
- Connection interruption → Retryable
- Slow response → Retryable with longer timeout
- Request failure → Depends on context

**C. Application Failures**
- Unexpected validation error → Non-retryable (bad input/logic)
- Failed API request (4xx client errors) → Usually non-retryable
- Delayed application response → Retryable
- Application state mismatch → Needs investigation, may be non-retryable

**D. Execution Failures**
- Worker process termination → Retryable via resume from persisted state
- Execution interruption between steps → Resume from last completed step
- Restart after persisted state → Resume mechanism
- Duplicate execution request → Idempotent (don't create duplicate runs)

### Retry Policy
- **Retryable:** Transient network/browser issues, recoverable process issues
- **Non-retryable:** Business validation failures, auth failures, missing required data, permanent errors
- **Max retries:** Configurable per scenario/step (default reasonable)
- **Backoff:** Exponential backoff (e.g., 1s, 2s, 4s)
- **Critical:** Never retry side-effecting actions blindly without idempotency check

---

## 5. Database Schema Design

### Core Entities

#### `scenarios`
```sql
id UUID PRIMARY KEY
name VARCHAR(255) NOT NULL
description TEXT
configuration JSONB NOT NULL  -- steps, retry policy, failure injection config
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
```

#### `test_runs`
```sql
id UUID PRIMARY KEY
scenario_id UUID REFERENCES scenarios(id)
status VARCHAR(50) NOT NULL  -- PENDING, RUNNING, PASSED, FAILED, RETRYING, RECOVERED, CANCELLED, INTERRUPTED
environment VARCHAR(100)
total_steps INTEGER
started_at TIMESTAMP WITH TIME ZONE
completed_at TIMESTAMP WITH TIME ZONE
worker_id VARCHAR(255)
metadata JSONB
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_test_runs_status (status)
INDEX idx_test_runs_scenario_id (scenario_id)
INDEX idx_test_runs_created_at (created_at)
```

#### `step_executions`
```sql
id UUID PRIMARY KEY
run_id UUID REFERENCES test_runs(id) ON DELETE CASCADE
step_id VARCHAR(255) NOT NULL  -- ID from scenario definition
status VARCHAR(50) NOT NULL
attempt_number INTEGER DEFAULT 1
started_at TIMESTAMP WITH TIME ZONE
completed_at TIMESTAMP WITH TIME ZONE
error_type VARCHAR(100)
error_message TEXT
error_details JSONB
verification_result JSONB
screenshot_path VARCHAR(512)
metadata JSONB
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

UNIQUE(run_id, step_id, attempt_number)
INDEX idx_step_executions_run_id (run_id)
INDEX idx_step_executions_status (status)
```

#### `action_ledger` (Critical for idempotency)
```sql
id UUID PRIMARY KEY
run_id UUID REFERENCES test_runs(id) ON DELETE CASCADE
step_id VARCHAR(255) NOT NULL
idempotency_key VARCHAR(255) NOT NULL UNIQUE  -- deterministic key
action_type VARCHAR(100) NOT NULL
status VARCHAR(50) NOT NULL  -- PENDING, EXECUTING, COMPLETED, FAILED, VERIFIED
attempt_number INTEGER DEFAULT 1
external_reference VARCHAR(255)  -- e.g., order_id from demo app
verification_status VARCHAR(50)
side_effect_occurred BOOLEAN DEFAULT FALSE
request_data JSONB
response_data JSONB
verified_at TIMESTAMP WITH TIME ZONE
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_action_ledger_run_id (run_id)
INDEX idx_action_ledger_idempotency_key (idempotency_key)
INDEX idx_action_ledger_external_reference (external_reference)
```

#### `execution_events`
```sql
id UUID PRIMARY KEY
run_id UUID REFERENCES test_runs(id) ON DELETE CASCADE
step_id VARCHAR(255)
event_type VARCHAR(100) NOT NULL  -- STEP_STARTED, STEP_COMPLETED, RETRY, FAILURE, RECOVERY, etc.
metadata JSONB
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_execution_events_run_id (run_id)
INDEX idx_execution_events_created_at (created_at)
```

#### `evidence`
```sql
id UUID PRIMARY KEY
run_id UUID REFERENCES test_runs(id) ON DELETE CASCADE
step_id VARCHAR(255)
artifact_type VARCHAR(50) NOT NULL  -- screenshot, log, network_trace, console_log
artifact_path VARCHAR(512) NOT NULL
artifact_size INTEGER
metadata JSONB
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_evidence_run_id (run_id)
```

#### `evaluations`
```sql
id UUID PRIMARY KEY
scenario_id UUID REFERENCES scenarios(id)
sample_size INTEGER NOT NULL
metrics JSONB NOT NULL  -- all computed metrics
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_evaluations_scenario_id (scenario_id)
```

#### `demo_app_orders` (in demo app DB/schema)
```sql
id UUID PRIMARY KEY
user_id UUID
order_number VARCHAR(50) UNIQUE
items JSONB
total_amount DECIMAL(10,2)
status VARCHAR(50)
idempotency_key VARCHAR(255) UNIQUE  -- server-side idempotency
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

INDEX idx_demo_orders_idempotency_key (idempotency_key)
```

### State Transitions

**TestRun Status Flow:**
```
PENDING → RUNNING → (PASSED | FAILED | CANCELLED)
                ↓
              RETRYING → RUNNING (retry attempt)
                ↓
              RECOVERED (if recovered from failure)
                ↓
              INTERRUPTED (if worker killed) → RUNNING (on resume)
```

**StepExecution Status Flow:**
```
PENDING → RUNNING → (PASSED | FAILED)
                ↓
              RETRYING → RUNNING (next attempt)
```

**ActionLedger Status Flow:**
```
PENDING → EXECUTING → (COMPLETED | FAILED)
                ↓
              VERIFIED (after postcondition check)
```

**Rules:**
- No arbitrary transitions
- INTERRUPTED runs can be resumed
- RETRYING means a retry is in progress/planned
- RECOVERED means failed but successfully recovered
- Once PASSED, status shouldn't regress

---

## 6. Implementation Plan (Phase by Phase)

### Phase 0: Research & Architecture ✓ (This document)
- [x] Inspect repository
- [x] Research Klarent public positioning
- [x] Identify engineering problems
- [x] Propose architecture
- [x] Identify failure modes & classification
- [x] Design DB schema & state transitions
- [x] Write implementation plan
- [x] Define acceptance tests

### Phase 1: Foundation
**Tasks:**
- [ ] Project structure setup
- [ ] FastAPI app initialization
- [ ] PostgreSQL connection/config
- [ ] Redis connection/config
- [ ] SQLAlchemy setup with models base
- [ ] Alembic initialization and first migration
- [ ] Pydantic settings management
- [ ] Structured logging (structlog or stdlib)
- [ ] Health check endpoints
- [ ] Docker Compose (app, postgres, redis)
- [ ] .env.example
- [ ] pyproject.toml with dependencies

**Deliverable:** Runnable foundation with health checks passing

### Phase 2: Demo Application
**Tasks:**
- [ ] Minimal e-commerce app (separate module or same app)
- [ ] User registration/login
- [ ] Product catalog (browse/search)
- [ ] Shopping cart
- [ ] Checkout flow
- [ ] Order creation with idempotency key support
- [ ] Order history
- [ ] Independent DB for demo app or shared with idempotency
- [ ] Routes/templates for demo app

**Deliverable:** Functional demo app for testing

### Phase 3: Execution Engine
**Tasks:**
- [ ] Scenario schema/definitions
- [ ] Step execution framework
- [ ] Playwright browser controller (with navigation restrictions)
- [ ] Action executors (navigate, click, fill, select, wait, assert_*, screenshot)
- [ ] Assertion engine with postcondition verification
- [ ] Test run manager
- [ ] State persistence after each step
- [ ] Execution events
- [ ] API endpoints for scenarios/runs
- [ ] Basic execution of scenarios A,B,C

**Deliverable:** Browser scenarios execute successfully

### Phase 4: Reliability (Critical)
**Tasks:**
- [ ] Failure injection framework (deterministic)
- [ ] Failure classification logic
- [ ] Retry manager with exponential backoff
- [ ] Action ledger for idempotency
- [ ] Idempotency manager
- [ ] Recovery orchestrator
- [ ] Persistent execution state
- [ ] Worker crash simulation and resume
- [ ] Postcondition-based recovery (check actual app state)
- [ ] Demo app idempotent order endpoint

**Deliverable:** Interrupted-checkout acceptance test passes (critical)

### Phase 5: Evaluation & Observability
**Tasks:**
- [ ] Evidence capture (screenshots, logs, events)
- [ ] Structured logging
- [ ] Evaluation engine with all metrics
- [ ] Repeated run experiments
- [ ] Failure categorization
- [ ] Metrics calculation from real data

**Deliverable:** Measurable reliability metrics

### Phase 6: Dashboard
**Tasks:**
- [ ] Overview page
- [ ] Scenarios page (view, configure)
- [ ] Execution details with timeline
- [ ] Failure laboratory
- [ ] Reliability evaluation page
- [ ] All data from backend (no hardcoding)

**Deliverable:** Usable developer dashboard

### Phase 7: Hardening
**Tasks:**
- [ ] Unit tests
- [ ] Integration tests
- [ ] E2E tests (including critical acceptance test)
- [ ] Concurrency testing
- [ ] Redis outage testing
- [ ] Browser cleanup
- [ ] Security review
- [ ] Docker clean build test
- [ ] Edge case fixes

**Deliverable:** All tests pass, reproducible from clean checkout

### Phase 8: Public Demo
**Tasks:**
- [ ] Comprehensive README
- [ ] Architecture diagram (text/ASCII or image)
- [ ] Database schema diagram
- [ ] API examples
- [ ] Screenshots of actual runs
- [ ] Failure recovery demo documentation
- [ ] Benchmark methodology
- [ ] Known limitations
- [ ] Engineering trade-offs
- [ ] Demo video script/materials

**Deliverable:** GitHub repo ready for inspection

---

## 7. Acceptance Tests

### Critical Acceptance Test (Must Pass)
**Test: Interrupted Checkout with Lost Response**

1. Start purchase workflow (Scenario B)
2. Successfully create an order in demo app
3. Simulate losing browser response after order created (network timeout/failure injection)
4. Interrupt execution (kill worker/process)
5. Restart execution worker
6. Resume workflow
7. Verify existing order in demo app
8. Complete run without creating another order

**Verification:**
- Database shows exactly 1 order in demo app
- ActionLedger shows 1 completed/verified side effect
- StepExecution shows recovery path taken
- TestRun ends in RECOVERED/PASSED
- No duplicate orders created

### Other Critical Tests
- [ ] Normal workflow succeeds (happy path)
- [ ] Transient failure triggers retry with backoff
- [ ] Permanent failure does not retry
- [ ] Max retries respected
- [ ] Worker restart resumes from last completed step
- [ ] Completed steps not repeated on resume
- [ ] Idempotent order creation prevents duplicates
- [ ] Redis outage doesn't break history retrieval
- [ ] Failure classification correct
- [ ] Evidence captured for all runs
- [ ] Metrics calculated from real data

---

## 8. Key Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| **Modular monolith** | Simpler to develop/debug, matches "start with modular monolith" in plan | Less scalable than microservices, but not needed for demo |
| **PostgreSQL as source of truth** | Durable, ACID transactions critical for idempotency | More complex than in-memory, but required |
| **Redis for coordination only** | Fast locks, but not required for history | If Redis down, can still read history from PG |
| **Deterministic failure injection** | Reproducible for testing/demos | Less "realistic" randomness, but required for reliability |
| **Postcondition verification** | Don't trust "no exception" from Playwright | More complex, but essential for trustworthiness |
| **Action ledger** | Track side effects explicitly | Extra complexity, but critical for duplicate prevention |
| **Server-rendered Jinja2** | Faster to build, matches plan guidance | Less interactive than SPA, but sufficient |
| **No LLM in core execution** | Deterministic, inspectable as specified | Less "agentic" looking, but more reliable and debuggable |

---

## 9. Security Considerations

- [ ] Environment variables for all secrets (no hardcoding)
- [ ] .env.example provided
- [ ] Restrict browser navigation to demo app only (SSRF prevention)
- [ ] No arbitrary Python code execution from scenarios
- [ ] Validate all scenario inputs
- [ ] Sanitize logs (no sensitive data)
- [ ] Clean up browser resources
- [ ] API input validation with Pydantic

---

## 10. Next Steps

**Phase 0 is complete.** I need your review and approval before proceeding to Phase 1 (Foundation).

Please review this architecture document and let me know:
1. Any changes or concerns
2. Approval to proceed to Phase 1
3. Any specific priorities or adjustments

Once approved, I'll start Phase 1, set up the project structure, initialize git commits properly, and after Phase 1 completion I'll raise a PR as requested.
