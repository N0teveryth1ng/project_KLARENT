import uuid
import hashlib
import json
import time

from fastapi import APIRouter, Depends, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database.session import get_db
from demo_app.models.cart import CartItem
from demo_app.models.order import Order

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


def _items_hash(items):
    return hashlib.sha256(json.dumps(items, sort_keys=True, default=str).encode()).hexdigest()


@router.get("/", response_class=HTMLResponse)
def checkout_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)
    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return templates.TemplateResponse(request=request, name="checkout.html", context={"request": request, "cart_items": cart_items, "total": total})


@router.post("/submit")
def submit_order(
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    fail_after_commit: str = Header(None, alias="X-Fail-After-Commit"),
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/demo/login", status_code=303)

    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    current_items = [
        {"product_id": str(item.product_id), "quantity": item.quantity, "price": float(item.product.price)}
        for item in cart_items
    ]

    if idempotency_key:
        existing_order = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing_order:
            # Idempotent retry: return original order. If there are cart items (unusual for retry),
            # validate payload matches; if comparison fails, be explicit.
            if cart_items:
                try:
                    current_hash = _items_hash(current_items)
                    orig_hash = _items_hash(existing_order.items)
                except Exception as e:
                    return JSONResponse(
                        {"error": "Idempotency payload comparison failed", "detail": str(e)},
                        status_code=409,
                    )
                if current_hash != orig_hash:
                    return JSONResponse(
                        {"error": "Idempotency key reused with different payload"},
                        status_code=409,
                    )
            return JSONResponse(
                {
                    "order_id": str(existing_order.id),
                    "order_number": existing_order.order_number,
                    "status": existing_order.status,
                    "message": "Order already exists",
                }
            )

    if not cart_items:
        return JSONResponse({"error": "Cart is empty"}, status_code=400)

    total = sum(item["price"] * item["quantity"] for item in current_items)

    try:
        order = Order(
            user_id=user_id,
            order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            items=current_items,
            total_amount=total,
            status="confirmed",
            idempotency_key=idempotency_key,
        )
        db.add(order)
        for item in cart_items:
            db.delete(item)
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing_order = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
            if existing_order:
                try:
                    existing_hash = _items_hash(existing_order.items)
                    new_hash = _items_hash(current_items)
                except Exception as e:
                    return JSONResponse(
                        {"error": "Idempotency payload comparison failed", "detail": str(e)},
                        status_code=409,
                    )
                if existing_hash != new_hash:
                    return JSONResponse(
                        {"error": "Idempotency key reused with different payload"},
                        status_code=409,
                    )
                return JSONResponse(
                    {
                        "order_id": str(existing_order.id),
                        "order_number": existing_order.order_number,
                        "status": existing_order.status,
                        "message": "Order already exists",
                    }
                )
        raise
    except Exception:
        db.rollback()
        raise

    # Simulate lost response after commit (order is durable)
    if fail_after_commit == "lost-response" or (idempotency_key and str(idempotency_key).startswith("LOST-")):
        time.sleep(10)
        raise HTTPException(status_code=504, detail="Connection lost after commit (simulated)")

    return JSONResponse(
        {"order_id": str(order.id), "order_number": order.order_number, "status": order.status}
    )
