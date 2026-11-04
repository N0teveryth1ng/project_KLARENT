from app.models import test_run, step_execution, scenario, action_ledger, execution_event, evidence
from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger
from app.models.execution_event import ExecutionEvent
from app.models.evidence import Evidence


def test_models_importable():
    assert TestRun.__tablename__ == "test_runs"
    assert StepExecution.__tablename__ == "step_executions"
    assert ActionLedger.__tablename__ == "action_ledger"
    assert ExecutionEvent.__tablename__ == "execution_events"
    assert Evidence.__tablename__ == "evidence"
