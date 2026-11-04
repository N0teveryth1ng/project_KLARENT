from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import health, scenarios, runs, evaluations, dashboard
from app.core.config import settings
from demo_app.routes import auth, products, cart, checkout, orders

app = FastAPI(
    title=settings.app_name,
    description="Agent QA Reliability & Recovery Platform",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(scenarios.router, prefix="/api/scenarios", tags=["scenarios"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(evaluations.router, prefix="/api/evaluations", tags=["evaluations"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(auth.router, prefix="/demo", tags=["demo-auth"])
app.include_router(products.router, prefix="/demo/products", tags=["demo-products"])
app.include_router(cart.router, prefix="/demo/cart", tags=["demo-cart"])
app.include_router(checkout.router, prefix="/demo/checkout", tags=["demo-checkout"])
app.include_router(orders.router, prefix="/demo/orders", tags=["demo-orders"])

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
        "demo": "/demo/products",
        "dashboard": "/dashboard/",
    }
