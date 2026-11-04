import sys
import asyncio
from app.database.session import SessionLocal
from app.execution.manager import TestRunManager
import uuid

if __name__ == "__main__":
    run_id = sys.argv[1]
    db = SessionLocal()
    try:
        manager = TestRunManager(db)
        asyncio.run(manager.execute_run(uuid.UUID(run_id)))
    finally:
        db.close()
