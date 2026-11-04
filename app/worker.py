import asyncio
import sys
from app.database.session import SessionLocal
from app.recovery.orchestrator import RecoveryOrchestrator
from app.execution.manager import TestRunManager


async def main():
    db = SessionLocal()
    try:
        orchestrator = RecoveryOrchestrator(db)
        await orchestrator.recover_incomplete_runs(TestRunManager)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
