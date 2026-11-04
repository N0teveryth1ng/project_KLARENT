from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from demo_app.models.product import Product

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
def products_page(request: Request, db: Session = Depends(get_db), search: str = None):
    query = db.query(Product)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    products = query.all()
    return templates.TemplateResponse("products.html", {"request": request, "products": products, "search": search})


@router.get("/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    return templates.TemplateResponse("product_detail.html", {"request": request, "product": product})
