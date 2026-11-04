from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class TestRunCreate(BaseModel):
    scenario_id: UUID
    environment: Optional[str] = "default"


class TestRunResponse(BaseModel):
    id: UUID
    scenario_id: UUID
    status: str
    environment: Optional[str] = None
    total_steps: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
