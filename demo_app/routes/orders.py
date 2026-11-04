from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from demo_app.models.order import Order

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


@router.get("/", response_class=HTMLResponse)
def orders_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return HTMLResponse("Not logged in", status_code=401)
    
    orders = db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})
