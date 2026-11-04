from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.evaluation.metrics import MetricsCalculator
from app.models.evaluation import Evaluation

router = APIRouter()


@router.get("/")
def get_evaluations(scenario_id: str = None, db: Session = Depends(get_db)):
    calculator = MetricsCalculator(db)
    metrics = calculator.calculate_metrics(scenario_id)
    
    # Save evaluation
    if scenario_id:
        eval = Evaluation(
            scenario_id=scenario_id,
            sample_size=metrics["sample_size"],
            metrics=metrics
        )
        db.add(eval)
        db.commit()
    
    return metrics


@router.get("/history")
def get_evaluation_history(scenario_id: str = None, db: Session = Depends(get_db)):
    query = db.query(Evaluation)
    if scenario_id:
        query = query.filter(Evaluation.scenario_id == scenario_id)
    return query.order_by(Evaluation.created_at.desc()).all()
