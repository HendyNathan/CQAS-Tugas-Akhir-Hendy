"""Regression coverage for CQAS authentication, project records, analysis, uploads, and reports."""
import io
import os
import time
import uuid

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
    assert response.status_code == 200, response.text
    assert session.cookies.get("access_token")
    return session


@pytest.fixture(scope="module")
def project(client):
    response = client.get(f"{BASE_URL}/api/projects")
    assert response.status_code == 200
    projects = response.json()
    demo = next((item for item in projects if item.get("code") == "NBS-DEMO"), None)
    assert demo and "Navapark Business Suites" in demo["name"]
    return demo


def test_auth_me_and_demo_dashboard(client, project):
    me = client.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "admin@cqas.local"
    dashboard = client.get(f"{BASE_URL}/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["projects"] >= 1


def test_create_project_persists(client):
    payload = {"name": f"TEST_CQAS_{uuid.uuid4().hex[:8]}", "code": "TEST-QA", "location": "Bandung", "description": "Regression project"}
    created = client.post(f"{BASE_URL}/api/projects", json=payload)
    assert created.status_code == 200 and created.json()["name"] == payload["name"]
    fetched = client.get(f"{BASE_URL}/api/projects/{created.json()['id']}")
    assert fetched.status_code == 200 and fetched.json()["code"] == "TEST-QA"


def test_manual_records_and_deterministic_analysis(client, project):
    pid = project["id"]
    strength = client.post(f"{BASE_URL}/api/projects/{pid}/records", json={"test_type": "strength", "record": {"sample_code": "TEST-S-001", "compressive_strength": 32, "planned_strength": 30}})
    assert strength.status_code == 200 and strength.json()["record"]["sample_code"] == "TEST-S-001"
    slump = client.post(f"{BASE_URL}/api/projects/{pid}/records", json={"test_type": "slump", "record": {"sample_code": "TEST-SL-001", "actual_slump": 100, "target_slump": 100}})
    assert slump.status_code == 200
    analysis = client.post(f"{BASE_URL}/api/projects/{pid}/analyze")
    assert analysis.status_code == 200
    assert any(row["assessment"]["status"] == "COMPLIANT" for row in analysis.json()["strength"]["records"])
    assert any(row["assessment"]["status"] == "COMPLIANT" for row in analysis.json()["slump"]["records"])


def test_report_download_and_upload_validation(client, project):
    pid = project["id"]
    report = client.get(f"{BASE_URL}/api/projects/{pid}/report")
    assert report.status_code == 200 and report.headers.get("content-type", "").startswith("application/pdf") and report.content[:4] == b"%PDF"
    bad = client.post(f"{BASE_URL}/api/projects/{pid}/upload", files={"file": ("bad.txt", b"not allowed", "text/plain")})
    assert bad.status_code == 400


def test_indonesian_excel_upload_review_and_import(client, project):
    frame = pd.DataFrame([["Kode", "Tanggal Cor", "Tanggal Uji", "Umur (hari)", "Luas Penampang (cm²)", "Berat (kg)", "Beban (kN)", "Kuat Tekan MPa (N/mm²)", "Pola Retak", "Keterangan"], ["TEST-ID-001", "01/01/2026", "29/01/2026", 28, 225, 12.3, 720, 32, "A", "TEST IMPORT"]])
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, header=False)
    upload = client.post(f"{BASE_URL}/api/projects/{project['id']}/upload", files={"file": ("TEST_indonesian.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert upload.status_code == 200, upload.text
    data = upload.json()
    # Extraction is now asynchronous (queued -> processing -> completed); poll the status endpoint.
    status = {}
    for _ in range(40):
        status = client.get(f"{BASE_URL}/api/projects/{project['id']}/documents/{data['id']}/status").json()
        if status.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.5)
    assert status.get("status") == "completed", status
    assert status["extraction"]["detected"] == 1
    record = status["extraction"]["records"][0]
    assert record["sample_code"] == "TEST-ID-001" and record["age_days"] == 28 and record["compressive_strength"] == 32
    finalized = client.post(f"{BASE_URL}/api/projects/{project['id']}/import/{data['id']}")
    assert finalized.status_code == 200 and finalized.json()["inserted"] == 1


def test_logout_invalidates_session():
    session = requests.Session()
    login = session.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@cqas.local", "password": "admin123"})
    assert login.status_code == 200
    assert session.post(f"{BASE_URL}/api/auth/logout").status_code == 200
    assert session.get(f"{BASE_URL}/api/auth/me").status_code == 401