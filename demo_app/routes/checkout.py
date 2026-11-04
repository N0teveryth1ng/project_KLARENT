import uuid
from fastapi import APIRouter, Depends, Request, Form, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from demo_app.models.cart import CartItem
from demo_app.models.order import Order

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


@router.get("/", response_class=HTMLResponse)
def checkout_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)
    
    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return templates.TemplateResponse("checkout.html", {"request": request, "cart_items": cart_items, "total": total})


@router.post("/submit")
def submit_order(
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(None, alias="Idempotency-Key")
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)
    
    # Check for existing order with this idempotency key
    if idempotency_key:
        existing_order = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing_order:
            return JSONResponse({
                "order_id": str(existing_order.id),
                "order_number": existing_order.order_number,
                "status": existing_order.status,
                "message": "Order already exists"
            })
    
    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    if not cart_items:
        raise Exception("Cart is empty")
    
    items = [{"product_id": str(item.product_id), "quantity": item.quantity, "price": float(item.product.price)} for item in cart_items]
    total = sum(item["price"] * item["quantity"] for item in items)
    
    order = Order(
        user_id=user_id,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        items=items,
        total_amount=total,
        status="confirmed",
        idempotency_key=idempotency_key
    )
    db.add(order)
    
    # Clear cart
    for item in cart_items:
        db.delete(item)
    
    db.commit()
    db.refresh(order)
    
    return JSONResponse({
        "order_id": str(order.id),
        "order_number": order.order_number,
        "status": order.status
    })
