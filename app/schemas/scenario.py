from pydantic import BaseModel
from typing import Any, Optional
from uuid import UUID


class StepConfig(BaseModel):
    step_id: str
    action_type: str
    target: Optional[str] = None
    input_data: Optional[dict] = None
    expected_outcome: Optional[dict] = None
    timeout: int = 30000
    retry_policy: Optional[dict] = None
    verification_conditions: Optional[list] = None


class ScenarioConfig(BaseModel):
    name: str
    description: Optional[str] = None
    steps: list[StepConfig]
    retry_policy: Optional[dict] = None
    failure_injection: Optional[dict] = None


class ScenarioResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    configuration: dict
    
    class Config:
        from_attributes = True
