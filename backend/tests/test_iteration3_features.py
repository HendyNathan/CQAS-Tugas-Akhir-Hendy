"""Regression coverage for secure sharing, filtered insights, and queued imports."""
import io
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest
import requests

from dotenv import dotenv_values
_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env["REACT_APP_BACKEND_URL"]).rstrip("/")


@pytest.fixture(scope="module")
def client():
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@cqas.local", "password": "admin123"})
    assert response.status_code == 200
    return session


@pytest.fixture(scope="module")
def project(client):
    projects = client.get(f"{BASE_URL}/api/projects").json()
    return next(item for item in projects if item.get("code") == "NBS-DEMO")


def test_share_token_public_disable_and_expiry(client, project):
    pid = project["id"]
    created = client.post(f"{BASE_URL}/api/projects/{pid}/shares", json={"permission": "VIEWER"})
    assert created.status_code == 200
    payload = created.json()
    assert len(payload["token"]) >= 40 and payload["share_path"].endswith(payload["token"])
    public = requests.get(f"{BASE_URL}/api/shared/{payload['token']}")
    assert public.status_code == 200 and public.json()["permission"] == "VIEWER"
    assert client.delete(f"{BASE_URL}/api/projects/{pid}/shares/{payload['id']}").status_code == 200
    assert requests.get(f"{BASE_URL}/api/shared/{payload['token']}").status_code == 404
    expired = client.post(f"{BASE_URL}/api/projects/{pid}/shares", json={"permission": "EDITOR", "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})
    assert expired.status_code == 200
    assert requests.get(f"{BASE_URL}/api/shared/{expired.json()['token']}").status_code == 410


def test_insights_filters_and_report_ready_shapes(client, project):
    pid = project["id"]
    tag = uuid.uuid4().hex[:6]
    supplier_a, supplier_b = f"Supplier A {tag}", f"Supplier B {tag}"
    for sample, supplier, location, age, date, status in [("TEST-I3-A", supplier_a, f"North {tag}", 7, "2026-02-01", "COMPLIANT"), ("TEST-I3-B", supplier_b, f"South {tag}", 28, "2026-03-01", "WARNING")]:
        response = client.post(f"{BASE_URL}/api/projects/{pid}/records", json={"test_type": "strength", "record": {"sample_code": sample, "supplier": supplier, "location": location, "age_days": age, "test_date": date, "compressive_strength": 31, "planned_strength": 30, "assessment": {"status": status}}})
        assert response.status_code == 200
    result = client.get(f"{BASE_URL}/api/projects/{pid}/insights", params={"supplier": supplier_a, "location": f"North {tag}", "age": 7, "date_from": "2026-01-01", "date_to": "2026-02-28"})
    assert result.status_code == 200
    data = result.json()
    assert data["total"] == 1 and data["filters"]["supplier"] == supplier_a
    for key in ("strength_by_age", "supplier_comparison", "anomaly_trends", "summary"):
        assert key in data
    assert data["summary"]["recommendation"]


def test_queued_indonesian_excel_reaches_completed_and_imports(client, project):
    frame = pd.DataFrame([["Kode", "Tanggal Cor", "Tanggal Uji", "Umur (hari)", "Kuat Tekan MPa"], [f"TEST-I3-{uuid.uuid4().hex[:5]}", "01/01/2026", "29/01/2026", 28, 32]])
    buf = io.BytesIO()
    frame.to_excel(buf, index=False, header=False)
    upload = client.post(f"{BASE_URL}/api/projects/{project['id']}/upload", files={"file": ("TEST_i3.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert upload.status_code == 200
    doc = upload.json()
    assert doc["status"] in {"queued", "processing", "completed"}
    status = None
    for _ in range(20):
        status = client.get(f"{BASE_URL}/api/projects/{project['id']}/documents/{doc['id']}/status").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.3)
    assert status["status"] == "completed" and status["extraction"]["detected"] == 1
    assert status["extraction"]["records"][0]["age_days"] == 28
    finalized = client.post(f"{BASE_URL}/api/projects/{project['id']}/import/{doc['id']}")
    assert finalized.status_code == 200 and finalized.json()["inserted"] == 1