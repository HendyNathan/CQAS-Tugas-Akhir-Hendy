"""Iteration 5: PDF report export regression + auth cookie flow."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {"email": "admin@cqas.local", "password": "admin123"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=CREDS, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def project_id(session):
    r = session.get(f"{API}/projects", timeout=60)
    assert r.status_code == 200, r.text[:300]
    projects = r.json()
    assert isinstance(projects, list) and projects, "no projects returned"
    demo = next((p for p in projects if "DEMO" in (p.get("name") or "") or p.get("code") == "NBS-DEMO"), projects[0])
    assert "_id" not in demo
    return demo["id"]


# --- Auth cookie flow ---
class TestAuthCookies:
    def test_login_sets_httponly_cookie(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=CREDS, timeout=60)
        assert r.status_code == 200, r.text[:300]
        raw = " ".join(r.raw.headers.get_all("Set-Cookie", []) if hasattr(r.raw, "headers") else [])
        assert "access_token" in s.cookies, f"access_token cookie missing; set-cookie={raw}"
        assert "httponly" in raw.lower()
        body = r.json()
        assert body.get("user", body).get("email") == CREDS["email"] or body.get("email") == CREDS["email"]

    def test_me_with_cookie(self, session):
        r = session.get(f"{API}/auth/me", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["email"] == CREDS["email"]
        assert "_id" not in data
        assert "password_hash" not in data and "hashed_password" not in data

    def test_me_without_cookie(self):
        r = requests.get(f"{API}/auth/me", timeout=60)
        assert r.status_code == 401
        assert r.json().get("detail") == "Not authenticated"

    def test_bcrypt_hash_format(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values as dv
        env = dv("/app/backend/.env")

        async def check():
            client = AsyncIOMotorClient(env["MONGO_URL"])
            user = await client[env["DB_NAME"]].users.find_one({"email": CREDS["email"]}, {"_id": 0})
            client.close()
            return user

        user = asyncio.get_event_loop().run_until_complete(check())
        assert user, "admin user not seeded"
        h = user.get("password_hash") or user.get("hashed_password") or ""
        assert h.startswith("$2b$"), f"unexpected hash prefix: {h[:4]}"


# --- Report PDF export ---
class TestReportExport:
    def test_report_authenticated_pdf(self, session, project_id):
        r = session.get(f"{API}/projects/{project_id}/report", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert r.content[:4] == b"%PDF", r.content[:40]
        assert "attachment" in r.headers.get("content-disposition", "")
        assert len(r.content) > 1000

    def test_report_lang_id(self, session, project_id):
        r = session.get(f"{API}/projects/{project_id}/report", params={"lang": "id"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_report_invalid_lang_falls_back(self, session, project_id):
        r = session.get(f"{API}/projects/{project_id}/report", params={"lang": "xx"}, timeout=120)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_report_no_cookie_401(self, project_id):
        r = requests.get(f"{API}/projects/{project_id}/report", timeout=60)
        assert r.status_code == 401
        assert r.json().get("detail") == "Not authenticated"

    def test_report_bad_cookie_401(self, project_id):
        r = requests.get(f"{API}/projects/{project_id}/report", cookies={"access_token": "garbage.token.value"}, timeout=60)
        assert r.status_code == 401, r.text[:200]

    def test_report_unknown_project_404(self, session):
        r = session.get(f"{API}/projects/00000000-0000-0000-0000-000000000000/report", timeout=60)
        assert r.status_code in (403, 404), f"{r.status_code} {r.text[:200]}"

    def test_report_bearer_token_also_works(self, project_id):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=CREDS, timeout=60)
        token = s.cookies.get("access_token")
        assert token
        r2 = requests.get(f"{API}/projects/{project_id}/report", headers={"Authorization": f"Bearer {token}"}, timeout=120)
        assert r2.status_code == 200, r2.text[:200]
        assert r2.content[:4] == b"%PDF"
