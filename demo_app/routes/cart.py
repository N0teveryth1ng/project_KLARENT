from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from demo_app.models.cart import CartItem
from demo_app.models.product import Product

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


@router.get("/", response_class=HTMLResponse)
def cart_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)
    
    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return templates.TemplateResponse("cart.html", {"request": request, "cart_items": cart_items, "total": total})


@router.post("/add")
def add_to_cart(request: Request, product_id: str = Form(...), quantity: int = Form(1), db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)
    
    cart_item = CartItem(user_id=user_id, product_id=product_id, quantity=quantity)
    db.add(cart_item)
    db.commit()
    return RedirectResponse(url="/demo/cart", status_code=303)
