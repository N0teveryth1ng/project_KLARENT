from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any

from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.models.action_ledger import ActionLedger


class MetricsCalculator:
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_metrics(self, scenario_id: str = None) -> Dict[str, Any]:
        query = self.db.query(TestRun)
        if scenario_id:
            query = query.filter(TestRun.scenario_id == scenario_id)
        
        runs = query.all()
        total_runs = len(runs)
        
        if total_runs == 0:
            return {
                "task_success_rate": 0,
                "recovery_rate": 0,
                "retry_success_rate": 0,
                "duplicate_side_effect_count": 0,
                "mean_execution_duration": 0,
                "failure_distribution": {},
                "flaky_test_rate": 0,
                "assertion_accuracy": 0,
                "sample_size": 0
            }
        
        successful = sum(1 for r in runs if r.status == "PASSED")
        recovered = sum(1 for r in runs if r.status == "RECOVERED")
        failed = sum(1 for r in runs if r.status == "FAILED")
        
        # Calculate durations
        durations = []
        for r in runs:
            if r.started_at and r.completed_at:
                duration = (r.completed_at - r.started_at).total_seconds()
                durations.append(duration)
        
        mean_duration = sum(durations) / len(durations) if durations else 0
        
        # Duplicate side effects
        duplicate_count = self.db.query(ActionLedger).filter(
            ActionLedger.side_effect_occurred == True
        ).count()
        # This is simplified - in reality track duplicates
        
        # Failure distribution
        failed_runs = [r for r in runs if r.status == "FAILED"]
        failure_dist = {}
        for r in failed_runs:
            failures = self.db.query(StepExecution).filter(
                StepExecution.run_id == r.id,
                StepExecution.status == "FAILED"
            ).all()
            for f in failures:
                error_type = f.error_type or "unknown"
                failure_dist[error_type] = failure_dist.get(error_type, 0) + 1
        
        task_success_rate = (successful / total_runs) * 100
        recovery_rate = (recovered / max(failed + recovered, 1)) * 100 if (failed + recovered) > 0 else 0
        
        return {
            "task_success_rate": round(task_success_rate, 2),
            "recovery_rate": round(recovery_rate, 2),
            "retry_success_rate": 0,  # Would need retry tracking
            "duplicate_side_effect_count": duplicate_count,
            "mean_execution_duration": round(mean_duration, 2),
            "failure_distribution": failure_dist,
            "flaky_test_rate": 0,  # Would need repeated runs analysis
            "assertion_accuracy": task_success_rate,  # Simplified
            "sample_size": total_runs,
            "successful_runs": successful,
            "failed_runs": failed,
            "recovered_runs": recovered
        }
