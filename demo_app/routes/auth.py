from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from demo_app.models.user import User
import hashlib

router = APIRouter()
templates = Jinja2Templates(directory="demo_app/templates")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"request": request})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if user exists
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=400, detail="User already exists")
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = User(username=username, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    response = RedirectResponse(url="/demo/login", status_code=303)
    return response


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = db.query(User).filter(User.username == username, User.password_hash == password_hash).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    response = RedirectResponse(url="/demo/products", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response
