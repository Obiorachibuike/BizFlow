from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)
def override_db():
    db = TestingSession()
    try: yield db
    finally: db.close()
app.dependency_overrides[get_db] = override_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    client.cookies.clear()
    yield
    client.cookies.clear()

def register(email="owner@example.com", business="Corner Shop"):
    r = client.post("/api/auth/register", json={"full_name":"Ada Owner", "email":email, "password":"correct-horse-42", "organization_name":business})
    assert r.status_code == 201, r.text
    return r.json()

def csrf():
    return {"X-CSRF-Token": client.cookies.get("bizflow_csrf")}

def test_account_product_receive_sale_and_dashboard():
    register()
    headers = csrf()
    r = client.post("/api/products", json={"name":"Rice 5kg", "sku":"RICE-5", "category":"Food", "price":"12500.00", "cost":"9800.00", "reorder_level":"3"}, headers=headers)
    assert r.status_code == 201, r.text
    p = r.json()
    assert float(p["stock"]) == 0
    r = client.post(f"/api/products/{p['id']}/receive", json={"quantity":"10", "note":"Initial delivery GRN 1"}, headers=headers)
    assert r.status_code == 201, r.text
    assert float(r.json()["stock"]) == 10
    sale = client.post("/api/sales/checkout", json={"items":[{"product_id":p["id"],"quantity":"2"}],"payment_method":"cash"}, headers={**headers,"Idempotency-Key":"sale-1"})
    assert sale.status_code == 201, sale.text
    assert float(sale.json()["total"]) == 25000
    assert float(client.get("/api/products").json()[0]["stock"]) == 8
    dashboard=client.get("/api/dashboard").json()
    assert dashboard["today_transactions"] == 1
    assert float(dashboard["today_sales"]) == 25000

def test_checkout_idempotency_prevents_duplicate_sale_and_stock_issue():
    register()
    headers={**csrf(),"Idempotency-Key":"replay-key"}
    p=client.post("/api/products",json={"name":"Soap","sku":"SOAP-01","price":"500.00","track_stock":True},headers=csrf()).json()
    client.post(f"/api/products/{p['id']}/receive",json={"quantity":"1","note":"Opening stock"},headers=csrf())
    payload={"items":[{"product_id":p["id"],"quantity":"1"}],"payment_method":"cash"}
    first=client.post("/api/sales/checkout",json=payload,headers=headers)
    second=client.post("/api/sales/checkout",json=payload,headers=headers)
    assert first.status_code==201 and second.status_code==201
    assert first.json()["id"]==second.json()["id"] and second.json()["replayed"] is True
    assert len(client.get("/api/sales").json())==1
    assert float(client.get("/api/products").json()[0]["stock"])==0
    exhausted=client.post("/api/sales/checkout",json={"items":[{"product_id":p["id"],"quantity":"1"}],"payment_method":"cash"},headers={**csrf(),"Idempotency-Key":"sale-two"})
    assert exhausted.status_code==409

def test_tenant_isolation_and_csrf():
    product=None
    register("first@example.com","First Org")
    product=client.post("/api/products",json={"name":"Private item","sku":"PRIVATE","price":"100.00"},headers=csrf())
    assert product.status_code==201
    client.post("/api/auth/logout", headers=csrf())
    register("second@example.com","Second Org")
    assert client.get("/api/products").json()==[]
    assert client.post(f"/api/products/{product.json()['id']}/receive",json={"quantity":"4","note":"Should fail"},headers=csrf()).status_code==404
    no_csrf=client.post("/api/products",json={"name":"No token","sku":"NOPE","price":"1.00"})
    assert no_csrf.status_code==403

def test_authentication_and_password_not_returned():
    data=register()
    assert "password_hash" not in str(data)
    client.post("/api/auth/logout", headers=csrf())
    bad=client.post("/api/auth/login",json={"email":"owner@example.com","password":"wrong-password"})
    assert bad.status_code==401
    good=client.post("/api/auth/login",json={"email":"owner@example.com","password":"correct-horse-42"})
    assert good.status_code==200

def test_unconfirmed_payment_and_idempotency_payload_conflict():
    register()
    p=client.post("/api/products",json={"name":"Consultation","sku":"CONSULT","price":"2500.00","track_stock":False},headers=csrf()).json()
    headers={**csrf(),"Idempotency-Key":"transfer-once"}
    result=client.post("/api/sales/checkout",json={"items":[{"product_id":p["id"],"quantity":"1"}],"payment_method":"bank_transfer"},headers=headers)
    assert result.status_code==201
    assert result.json()["status"]=="pending"
    conflict=client.post("/api/sales/checkout",json={"items":[{"product_id":p["id"],"quantity":"2"}],"payment_method":"bank_transfer"},headers=headers)
    assert conflict.status_code==409
    unsupported_card=client.post("/api/sales/checkout",json={"items":[{"product_id":p["id"],"quantity":"1"}],"payment_method":"card"},headers={**csrf(),"Idempotency-Key":"card-unconfigured"})
    assert unsupported_card.status_code==422
