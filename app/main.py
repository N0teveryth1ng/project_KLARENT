from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import health
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Agent QA Reliability & Recovery Platform",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
except Exception:
    pass


@app.get("/")
def root():
    return {
        "message": "Agent Reliability Lab",
        "docs": "/docs",
        "health": "/health",
    }
