import hashlib, json, os, secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from .database import Base, engine, get_db
from . import models as m

SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only-change-me")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
if os.getenv("ENVIRONMENT") == "production" and SECRET_KEY == "local-development-only-change-me":
    raise RuntimeError("Set a unique SECRET_KEY before starting in production")
SESSION_COOKIE = "bizflow_session"
CSRF_COOKIE = "bizflow_csrf"
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="bizflow-session-v1")
password_hasher = PasswordHasher()

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Local convenience; production and Compose deployments use Alembic migrations.
    if os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true":
        Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="BizFlow Africa API", version="0.1.0", description="Tenant-scoped SME operations API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","), allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])

def set_session(response: Response, user_id: int, org_id: int):
    token = serializer.dumps({"uid": user_id, "org": org_id})
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=60 * 60 * 12, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=COOKIE_SECURE, samesite="lax", max_age=60 * 60 * 12, path="/")

def get_identity(request: Request, db: Session) -> tuple[m.User, m.Organization, m.Membership]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue")
    try:
        data = serializer.loads(token, max_age=60 * 60 * 12)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Session expired; sign in again")
    user = db.get(m.User, data.get("uid"))
    org = db.get(m.Organization, data.get("org"))
    membership = db.scalar(select(m.Membership).where(m.Membership.user_id == data.get("uid"), m.Membership.organization_id == data.get("org")))
    if not user or not user.active or not org or not membership:
        raise HTTPException(401, "Account or organization access is unavailable")
    return user, org, membership

def auth(request: Request, db: Session = Depends(get_db)):
    return get_identity(request, db)

def require_csrf(request: Request):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.url.path not in {"/api/auth/register", "/api/auth/login"}:
        cookie = request.cookies.get(CSRF_COOKIE)
        header = request.headers.get("X-CSRF-Token")
        if not cookie or not header or not secrets.compare_digest(cookie, header):
            raise HTTPException(403, "CSRF token missing or invalid")

@app.get("/health")
def health():
    return {"status": "ok"}

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    organization_name: str = Field(min_length=2, max_length=180)
    currency: str = Field(default="NGN", pattern=r"^[A-Z]{3}$")
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    sku: str = Field(min_length=1, max_length=80)
    category: str = Field(default="Uncategorized", max_length=100)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    track_stock: bool = True
class AdjustmentIn(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    note: str = Field(min_length=2, max_length=500)
class CheckoutLine(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
class CheckoutIn(BaseModel):
    items: list[CheckoutLine] = Field(min_length=1, max_length=100)
    payment_method: str = Field(pattern="^(cash|bank_transfer|credit)$")

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
class OrganizationOut(BaseModel):
    id: int
    name: str
    currency: str
    timezone: str
class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sku: str
    category: str
    price: Decimal
    cost: Decimal
    reorder_level: Decimal
    track_stock: bool
    stock: Decimal = Decimal("0")

def current_stock(db: Session, org_id: int, product_id: int) -> Decimal:
    value = db.scalar(select(func.coalesce(func.sum(m.StockMovement.quantity), Decimal("0.000"))).where(m.StockMovement.organization_id == org_id, m.StockMovement.product_id == product_id))
    return Decimal(str(value if value is not None else "0.000")).quantize(Decimal("0.001"))

def product_dict(db: Session, p: m.Product):
    return {"id": p.id, "name": p.name, "sku": p.sku, "category": p.category, "price": p.price, "cost": p.cost, "reorder_level": p.reorder_level, "track_stock": p.track_stock, "stock": current_stock(db, p.organization_id, p.id) if p.track_stock else Decimal("0")}

@app.post("/api/auth/register", status_code=201)
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(m.User).where(m.User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = m.User(email=email, full_name=data.full_name.strip(), password_hash=password_hasher.hash(data.password))
    org = m.Organization(name=data.organization_name.strip(), currency=data.currency)
    try:
        db.add_all([user, org]); db.flush()
        db.add(m.Membership(user_id=user.id, organization_id=org.id, role="owner")); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Unable to create account")
    set_session(response, user.id, org.id)
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name}, "organization": {"id": org.id, "name": org.name, "currency": org.currency, "timezone": org.timezone}}

@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(m.User).where(m.User.email == data.email.lower()))
    if not user or not user.active:
        raise HTTPException(401, "Email or password is incorrect")
    try:
        password_hasher.verify(user.password_hash, data.password)
    except VerifyMismatchError:
        raise HTTPException(401, "Email or password is incorrect")
    membership = db.scalar(select(m.Membership).where(m.Membership.user_id == user.id).order_by(m.Membership.id))
    if not membership:
        raise HTTPException(403, "No organization membership is available")
    org = db.get(m.Organization, membership.organization_id)
    set_session(response, user.id, org.id)
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name}, "organization": {"id": org.id, "name": org.name, "currency": org.currency, "timezone": org.timezone}}

@app.post("/api/auth/logout", dependencies=[Depends(require_csrf)])
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/"); response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}

@app.get("/api/auth/me")
def me(identity=Depends(auth)):
    user, org, membership = identity
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name}, "organization": {"id": org.id, "name": org.name, "currency": org.currency, "timezone": org.timezone}, "role": membership.role}

@app.get("/api/products")
def list_products(q: str | None = None, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, _ = identity
    query = select(m.Product).where(m.Product.organization_id == org.id, m.Product.active.is_(True)).order_by(m.Product.name).limit(200)
    if q:
        term = f"%{q.strip()}%"
        query = query.where((m.Product.name.ilike(term)) | (m.Product.sku.ilike(term)))
    return [product_dict(db, p) for p in db.scalars(query).all()]

@app.post("/api/products", status_code=201, dependencies=[Depends(require_csrf)])
def create_product(data: ProductIn, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, membership = identity
    if membership.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "You do not have permission to manage products")
    p = m.Product(organization_id=org.id, name=data.name.strip(), sku=data.sku.strip(), category=data.category.strip(), price=data.price, cost=data.cost, reorder_level=data.reorder_level, track_stock=data.track_stock)
    db.add(p)
    try: db.commit(); db.refresh(p)
    except IntegrityError: db.rollback(); raise HTTPException(409, "SKU already exists in this organization")
    return product_dict(db, p)

@app.post("/api/products/{product_id}/receive", status_code=201, dependencies=[Depends(require_csrf)])
def receive_stock(product_id: int, data: AdjustmentIn, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, membership = identity
    if membership.role not in {"owner", "admin", "manager"}: raise HTTPException(403, "You do not have permission to adjust stock")
    p = db.scalar(select(m.Product).where(m.Product.id == product_id, m.Product.organization_id == org.id, m.Product.active.is_(True)))
    if not p or not p.track_stock: raise HTTPException(404, "Stock-tracked product not found")
    movement = m.StockMovement(organization_id=org.id, product_id=p.id, quantity=data.quantity, movement_type="receipt", note=data.note, created_by=user.id)
    db.add(movement); db.commit(); db.refresh(movement)
    return {"id": movement.id, "product_id": p.id, "quantity": movement.quantity, "stock": current_stock(db, org.id, p.id)}

@app.get("/api/inventory/movements")
def movements(limit: int = 100, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, _ = identity
    rows = db.execute(select(m.StockMovement, m.Product.name, m.Product.sku).join(m.Product, m.StockMovement.product_id == m.Product.id).where(m.StockMovement.organization_id == org.id).order_by(m.StockMovement.created_at.desc()).limit(min(max(limit, 1), 250))).all()
    return [{"id": x.id, "product_id": x.product_id, "product_name": name, "sku": sku, "quantity": x.quantity, "type": x.movement_type, "note": x.note, "created_at": x.created_at} for x, name, sku in rows]

@app.post("/api/sales/checkout", status_code=201, dependencies=[Depends(require_csrf)])
def checkout(data: CheckoutIn, request: Request, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, membership = identity
    if data.payment_method == "credit" and membership.role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Credit sales require manager approval")
    key = request.headers.get("Idempotency-Key")
    if not key or len(key) > 128: raise HTTPException(400, "A valid Idempotency-Key header is required")
    quantities: dict[int, Decimal] = {}
    for line in data.items: quantities[line.product_id] = quantities.get(line.product_id, Decimal("0")) + line.quantity
    request_fingerprint = hashlib.sha256(json.dumps({"payment_method": data.payment_method, "items": [[pid, str(qty)] for pid, qty in sorted(quantities.items())]}, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(m.IdempotencyRecord).where(m.IdempotencyRecord.organization_id == org.id, m.IdempotencyRecord.key == key))
    if existing and existing.request_hash and existing.request_hash != request_fingerprint:
        raise HTTPException(409, "This idempotency key was already used for a different checkout")
    if existing and existing.sale_id:
        old = db.get(m.Sale, existing.sale_id)
        return {"id": old.id, "total": old.total, "payment_method": old.payment_method, "status": old.status, "replayed": True}
    try:
        record = existing or m.IdempotencyRecord(organization_id=org.id, key=key)
        record.request_hash = request_fingerprint
        if not existing: db.add(record); db.flush()
        sale = m.Sale(organization_id=org.id, user_id=user.id, total=Decimal("0.00"), payment_method=data.payment_method, status="paid" if data.payment_method == "cash" else ("pending" if data.payment_method == "bank_transfer" else "unpaid"))
        db.add(sale); db.flush()
        total = Decimal("0.00")
        for product_id, quantity in sorted(quantities.items()):
            p = db.scalar(select(m.Product).where(m.Product.id == product_id, m.Product.organization_id == org.id, m.Product.active.is_(True)).with_for_update())
            if not p: raise HTTPException(404, f"Product {product_id} not found in this organization")
            if p.track_stock and current_stock(db, org.id, p.id) < quantity: raise HTTPException(409, f"Insufficient stock for {p.name}")
            line_total = (p.price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += line_total
            db.add(m.SaleItem(sale_id=sale.id, product_id=p.id, product_name=p.name, quantity=quantity, unit_price=p.price, line_total=line_total))
            if p.track_stock: db.add(m.StockMovement(organization_id=org.id, product_id=p.id, quantity=-quantity, movement_type="sale", reference=str(sale.id), note=f"Sale #{sale.id}", created_by=user.id))
        sale.total = total; record.sale_id = sale.id
        db.commit(); db.refresh(sale)
        return {"id": sale.id, "total": sale.total, "payment_method": sale.payment_method, "status": sale.status, "replayed": False}
    except HTTPException:
        db.rollback(); raise
    except IntegrityError:
        db.rollback()
        prior = db.scalar(select(m.IdempotencyRecord).where(m.IdempotencyRecord.organization_id == org.id, m.IdempotencyRecord.key == key))
        if prior and prior.request_hash and prior.request_hash != request_fingerprint:
            raise HTTPException(409, "This idempotency key was already used for a different checkout")
        if prior and prior.sale_id:
            old = db.get(m.Sale, prior.sale_id)
            return {"id": old.id, "total": old.total, "payment_method": old.payment_method, "status": old.status, "replayed": True}
        raise HTTPException(409, "Checkout conflict; retry with the same idempotency key")

@app.get("/api/sales")
def list_sales(limit: int = 50, db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, _ = identity
    sales = db.scalars(select(m.Sale).options(joinedload(m.Sale.items)).where(m.Sale.organization_id == org.id).order_by(m.Sale.created_at.desc()).limit(min(max(limit, 1), 200))).unique().all()
    return [{"id": s.id, "total": s.total, "payment_method": s.payment_method, "status": s.status, "created_at": s.created_at, "items": [{"name": i.product_name, "quantity": i.quantity, "unit_price": i.unit_price, "line_total": i.line_total} for i in s.items]} for s in sales]

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), identity=Depends(auth)):
    user, org, _ = identity
    try:
        org_timezone = ZoneInfo(org.timezone)
    except ZoneInfoNotFoundError:
        org_timezone = timezone.utc
    local_today = datetime.now(timezone.utc).astimezone(org_timezone).date()
    start = datetime.combine(local_today, datetime.min.time(), org_timezone).astimezone(timezone.utc)
    end = (datetime.combine(local_today, datetime.min.time(), org_timezone) + timedelta(days=1)).astimezone(timezone.utc)
    sales = db.scalars(select(m.Sale).where(m.Sale.organization_id == org.id, m.Sale.created_at >= start, m.Sale.created_at < end, m.Sale.status == "paid")).all()
    product_rows = db.scalars(select(m.Product).where(m.Product.organization_id == org.id, m.Product.active.is_(True)).order_by(m.Product.name).limit(500)).all()
    low_stock = [{"id": p.id, "name": p.name, "sku": p.sku, "stock": current_stock(db, org.id, p.id), "reorder_level": p.reorder_level} for p in product_rows if p.track_stock and current_stock(db, org.id, p.id) <= p.reorder_level]
    recent = db.execute(select(m.Sale, m.User.full_name).join(m.User, m.Sale.user_id == m.User.id).where(m.Sale.organization_id == org.id).order_by(m.Sale.created_at.desc()).limit(5)).all()
    return {"currency": org.currency, "date": local_today.isoformat(), "today_sales": sum((s.total for s in sales), Decimal("0.00")), "today_transactions": len(sales), "low_stock_count": len(low_stock), "low_stock": low_stock[:6], "recent_sales": [{"id": sale.id, "total": sale.total, "payment_method": sale.payment_method, "status": sale.status, "created_at": sale.created_at, "cashier": name} for sale, name in recent], "product_count": len(product_rows), "empty_state": not bool(sales)}
