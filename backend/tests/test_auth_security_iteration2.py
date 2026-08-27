"""Security regression coverage for auth cookies, explicit CORS, and login lockout."""
import os
import uuid

import requests


from dotenv import dotenv_values
_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env["REACT_APP_BACKEND_URL"]).rstrip("/")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "https://slump-check.preview.emergentagent.com")


def test_login_sets_httponly_cookie_and_me_returns_safe_user():
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@cqas.local", "password": "admin123"},
    )
    assert response.status_code == 200
    cookie = session.cookies.get("access_token")
    assert cookie
    cookie_header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header
    me = session.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@cqas.local"
    assert "password_hash" not in me.json()


def test_cors_allows_configured_origin_with_credentials():
    response = requests.options(
        f"{BASE_URL}/api/auth/me",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_unknown_identifier_locks_after_five_failures():
    email = f"TEST_LOCKOUT_{uuid.uuid4().hex}@example.invalid"
    session = requests.Session()
    for _ in range(5):
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        assert response.status_code == 401
    locked = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert locked.status_code == 429