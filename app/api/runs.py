from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database.session import get_db
from app.models.test_run import TestRun
from app.models.step_execution import StepExecution
from app.schemas.test_run import TestRunCreate, TestRunResponse
from app.execution.manager import TestRunManager

router = APIRouter()


@router.post("/", response_model=TestRunResponse)
async def create_run(run_data: TestRunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    manager = TestRunManager(db)
    run = await manager.create_run(run_data.scenario_id, run_data.environment)
    background_tasks.add_task(manager.execute_run, run.id)
    return run


@router.get("/", response_model=List[TestRunResponse])
def list_runs(db: Session = Depends(get_db)):
    return db.query(TestRun).all()


@router.get("/{run_id}", response_model=TestRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/steps")
def get_run_steps(run_id: str, db: Session = Depends(get_db)):
    steps = db.query(StepExecution).filter(StepExecution.run_id == run_id).all()
    return steps
