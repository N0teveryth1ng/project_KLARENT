from sqlalchemy.orm import Session
from app.models.evidence import Evidence
from app.core.logging import logger


class EvidenceCapture:
    def __init__(self, db: Session):
        self.db = db
    
    def capture_screenshot(self, run_id: str, step_id: str, path: str, size: int = None):
        evidence = Evidence(
            run_id=run_id,
            step_id=step_id,
            artifact_type="screenshot",
            artifact_path=path,
            artifact_size=size
        )
        self.db.add(evidence)
        self.db.commit()
        logger.info("Screenshot evidence captured", path=path)
        return evidence
    
    def capture_log(self, run_id: str, step_id: str, log_content: str):
        evidence = Evidence(
            run_id=run_id,
            step_id=step_id,
            artifact_type="log",
            artifact_path="inline",
            evidence_metadata={"content": log_content}
        )
        self.db.add(evidence)
        self.db.commit()
        return evidence
    
    def get_evidence(self, run_id: str):
        return self.db.query(Evidence).filter(Evidence.run_id == run_id).all()
