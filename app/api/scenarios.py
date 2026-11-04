from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.models.scenario import Scenario
from app.schemas.scenario import ScenarioConfig, ScenarioResponse

router = APIRouter()


@router.post("/", response_model=ScenarioResponse)
def create_scenario(scenario: ScenarioConfig, db: Session = Depends(get_db)):
    db_scenario = Scenario(
        name=scenario.name,
        description=scenario.description,
        configuration=scenario.model_dump()
    )
    db.add(db_scenario)
    db.commit()
    db.refresh(db_scenario)
    return db_scenario


@router.get("/", response_model=List[ScenarioResponse])
def list_scenarios(db: Session = Depends(get_db)):
    return db.query(Scenario).all()


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario
