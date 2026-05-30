import uuid
import requests

BASE = "http://localhost:8000"
uid = str(uuid.uuid4())
tid = str(uuid.uuid4())

# 1. Register
r = requests.post(f"{BASE}/auth/register", json={
    "username": "testuser_smoke",
    "correo": "test@test.com",
    "password": "secret123",
    "usuario_id": uid,
    "tapo_id": tid,
})
assert r.status_code == 201, f"Register failed: {r.status_code} {r.text}"
token = r.json()["access_token"]
print("✅ POST /auth/register →", r.status_code, r.json()["username"])

# 2. Login with same credentials
r = requests.post(f"{BASE}/auth/login", json={"username": "testuser_smoke", "password": "secret123"})
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
print("✅ POST /auth/login    →", r.status_code, r.json()["username"])

# 3. 409 on duplicate register
r = requests.post(f"{BASE}/auth/register", json={
    "username": "testuser_smoke", "correo": "x@x.com", "password": "x",
    "usuario_id": str(uuid.uuid4()), "tapo_id": str(uuid.uuid4()),
})
assert r.status_code == 409, f"Expected 409, got {r.status_code}"
print("✅ Duplicate register → 409 Conflict (correct)")

# 4. Health check
r = requests.get(f"{BASE}/")
assert r.json()["status"] == "ok"
print("✅ GET /              →", r.json())