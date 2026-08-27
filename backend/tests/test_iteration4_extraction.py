"""Iteration 4 coverage: dual auth, field synonyms config, robust Indonesian Excel extraction,
manual column mapping overrides, import + analyze, sharing, upload validation, and PDF OCR."""
import io
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = _base.rstrip("/")

ADMIN = {"email": "admin@cqas.local", "password": "admin123"}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PART55_HEADERS = [
    "No", "Kode", "Tanggal Cor", "Tanggal Uji", "Umur (hari)",
    "Luas Penampang (cm²)", "Berat (kg)", "Beban (kN)",
    "Kuat Tekan MPa (N/mm²)", "Pola Retak", "Keterangan",
]
PART55_ROWS = [
    [1, "BU-01", "01/01/2026", "08/01/2026", 7, 225, 8.1, 480, 21.3, "Kerucut", "DEMO"],
    [2, "BU-02", "01/01/2026", "29/01/2026", 28, 225, 8.2, 720, 32.0, "Kerucut", "DEMO"],
    [3, "BU-03", "02/01/2026", "30/01/2026", 28, 225, 8.3, 745, 33.1, "Kolom", "DEMO"],
]


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def client():
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if response.status_code != 200:
        pytest.fail(f"Admin login failed: {response.status_code} {response.text[:300]}")
    return session


@pytest.fixture(scope="module")
def project(client):
    response = client.post(f"{BASE_URL}/api/projects", json={
        "name": f"TEST_ITER4 {uuid.uuid4().hex[:6]}", "code": "TEST-ITER4", "location": "Bandung",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _xlsx(headers, rows):
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame([headers] + rows).to_excel(buf, index=False, header=False)
    return buf.getvalue()


def _upload(client, project_id, name, content, mime=XLSX_MIME):
    return client.post(f"{BASE_URL}/api/projects/{project_id}/upload",
                       files={"file": (name, content, mime)})


def _wait(client, project_id, doc_id, attempts=60, delay=1.0):
    status = {}
    for _ in range(attempts):
        response = client.get(f"{BASE_URL}/api/projects/{project_id}/documents/{doc_id}/status")
        assert response.status_code == 200, response.text
        status = response.json()
        if status.get("status") in {"completed", "failed"}:
            return status
        time.sleep(delay)
    return status


# ---------------- module: auth ----------------
class TestAuth:
    def test_login_sets_httponly_cookie(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["email"] == ADMIN["email"]
        assert "password_hash" not in body and "_id" not in body
        cookie = next((c for c in session.cookies if c.name == "access_token"), None)
        assert cookie is not None, "access_token cookie not set"
        assert cookie.has_nonstandard_attr("HttpOnly") or "httponly" in str(response.headers.get("set-cookie", "")).lower()

    def test_me_returns_admin(self, client):
        response = client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        assert response.json()["email"] == ADMIN["email"]

    def test_me_unauthenticated_is_401(self):
        assert requests.get(f"{BASE_URL}/api/auth/me").status_code == 401

    def test_google_session_requires_session_id(self):
        response = requests.post(f"{BASE_URL}/api/auth/google/session", json={})
        assert response.status_code == 400, response.text

    def test_google_session_rejects_bogus_session_id(self):
        response = requests.post(f"{BASE_URL}/api/auth/google/session",
                                 headers={"X-Session-ID": "bogus-" + uuid.uuid4().hex})
        assert response.status_code == 401, response.text

    def test_logout_clears_session(self):
        session = requests.Session()
        assert session.post(f"{BASE_URL}/api/auth/login", json=ADMIN).status_code == 200
        assert session.get(f"{BASE_URL}/api/auth/me").status_code == 200
        assert session.post(f"{BASE_URL}/api/auth/logout").status_code == 200
        assert session.get(f"{BASE_URL}/api/auth/me").status_code == 401


# ---------------- module: config ----------------
class TestFieldSynonyms:
    def test_seventeen_canonical_fields(self):
        response = requests.get(f"{BASE_URL}/api/config/field-synonyms")
        assert response.status_code == 200
        data = response.json()
        assert len(data["fields"]) == 17, data["fields"]
        for field in data["fields"]:
            assert isinstance(data["synonyms"][field], list) and data["synonyms"][field]
        for expected in ("compressive_strength", "crack_pattern", "supplier", "age_days"):
            assert expected in data["fields"]


# ---------------- module: projects ----------------
class TestProjects:
    def test_created_project_is_owned_and_listed(self, client, project):
        assert project["members"][0]["role"] == "OWNER"
        listed = client.get(f"{BASE_URL}/api/projects").json()
        assert any(p["id"] == project["id"] for p in listed)
        detail = client.get(f"{BASE_URL}/api/projects/{project['id']}")
        assert detail.status_code == 200 and detail.json()["role"] == "OWNER"


# ---------------- module: extraction (PART 55 Indonesian Excel) ----------------
class TestPart55Extraction:
    @pytest.fixture(scope="class")
    def document(self, client, project):
        response = _upload(client, project["id"], "TEST_part55.xlsx", _xlsx(PART55_HEADERS, PART55_ROWS))
        assert response.status_code == 200, response.text
        doc = response.json()
        assert doc["status"] == "queued", doc
        assert "storage_path" not in doc and "_id" not in doc
        status = _wait(client, project["id"], doc["id"])
        assert status["status"] == "completed", status.get("error")
        return status

    def test_all_eleven_columns_mapped(self, document):
        table = document["extraction"]["tables"][0]
        assert table["test_type"] == "strength"
        assert len(table["used_columns"]) == 11, [c["header"] for c in table["used_columns"]]
        assert table["unused_columns"] == [], table["unused_columns"]

    def test_detected_matches_row_count(self, document):
        assert document["extraction"]["detected"] == len(PART55_ROWS)

    def test_values_normalized(self, document):
        records = document["extraction"]["records"]
        second = next(r for r in records if r["sample_code"] == "BU-02")
        assert second["age_days"] == 28
        assert second["compressive_strength"] == 32.0
        assert second["casting_date"] == "2026-01-01"
        assert second["test_date"] == "2026-01-29"
        assert second["crack_pattern"] == "Kerucut"
        assert second["assigned_test_type"] == "strength"


# ---------------- module: manual mapping overrides ----------------
class TestMappingOverrides:
    def test_test_type_override_preserves_detected(self, client, project):
        response = _upload(client, project["id"], "TEST_maptype.xlsx", _xlsx(PART55_HEADERS, PART55_ROWS))
        doc = response.json()
        before = _wait(client, project["id"], doc["id"])
        assert before["status"] == "completed"
        detected = before["extraction"]["detected"]
        override = client.post(
            f"{BASE_URL}/api/projects/{project['id']}/documents/{doc['id']}/mapping",
            json={"overrides": [{"table_index": 0, "test_type": "strength"}]},
        )
        assert override.status_code == 200, override.text
        payload = override.json()
        assert payload["detected"] == detected
        assert payload["tables"][0]["test_type"] == "strength"
        persisted = client.get(f"{BASE_URL}/api/projects/{project['id']}/documents/{doc['id']}/status").json()
        assert persisted["extraction"]["detected"] == detected
        assert "mapping_updated_at" in persisted

    def test_unmapped_column_can_be_assigned_supplier(self, client, project):
        headers = ["Kode", "Tanggal Uji", "Umur (hari)", "Kuat Tekan MPa", "Shift Kerja"]
        rows = [["MAP-01", "29/01/2026", 28, 31.5, "PT Beton Jaya"],
                ["MAP-02", "29/01/2026", 28, 30.1, "PT Beton Jaya"]]
        doc = _upload(client, project["id"], "TEST_mapcol.xlsx", _xlsx(headers, rows)).json()
        status = _wait(client, project["id"], doc["id"])
        assert status["status"] == "completed"
        unused = status["extraction"]["tables"][0]["unused_columns"]
        assert unused, "expected 'Shift Kerja' to remain unmapped"
        target = unused[0]["column_index"]
        override = client.post(
            f"{BASE_URL}/api/projects/{project['id']}/documents/{doc['id']}/mapping",
            json={"overrides": [{"table_index": 0, "column_index": target, "field": "supplier"}]},
        )
        assert override.status_code == 200, override.text
        payload = override.json()
        assert payload["detected"] == len(rows)
        assert any(c["field"] == "supplier" for c in payload["tables"][0]["used_columns"])
        assert all(r.get("supplier") == "PT Beton Jaya" for r in payload["records"]), payload["records"]

    def test_mapping_404_for_unknown_document(self, client, project):
        response = client.post(
            f"{BASE_URL}/api/projects/{project['id']}/documents/{uuid.uuid4()}/mapping",
            json={"overrides": []},
        )
        assert response.status_code == 404


# ---------------- module: import + analyze ----------------
class TestImportAndAnalyze:
    def test_import_respects_assigned_test_type_then_analyze(self, client, project):
        pid = project["id"]
        doc = _upload(client, pid, "TEST_import.xlsx", _xlsx(PART55_HEADERS, PART55_ROWS)).json()
        status = _wait(client, pid, doc["id"])
        assert status["status"] == "completed"
        imported = client.post(f"{BASE_URL}/api/projects/{pid}/import/{doc['id']}")
        assert imported.status_code == 200, imported.text
        assert imported.json()["inserted"] == len(PART55_ROWS)

        slump_doc = _upload(client, pid, "TEST_slump.xlsx", _xlsx(
            ["Kode", "Tanggal Uji", "Slump Aktual (mm)", "Slump Rencana (mm)"],
            [["SL-01", "05/01/2026", 100, 100], ["SL-02", "06/01/2026", 145, 100]],
        )).json()
        slump_status = _wait(client, pid, slump_doc["id"])
        assert slump_status["status"] == "completed"
        assert slump_status["extraction"]["tables"][0]["test_type"] == "slump"
        slump_import = client.post(f"{BASE_URL}/api/projects/{pid}/import/{slump_doc['id']}")
        assert slump_import.status_code == 200 and slump_import.json()["inserted"] == 2

        detail = client.get(f"{BASE_URL}/api/projects/{pid}").json()
        types = [r["test_type"] for r in detail["records"] if r.get("document_id") in {doc["id"], slump_doc["id"]}]
        assert types.count("strength") == 3 and types.count("slump") == 2

        analyzed = client.post(f"{BASE_URL}/api/projects/{pid}/analyze")
        assert analyzed.status_code == 200, analyzed.text
        result = analyzed.json()
        assert "slump" in result and "strength" in result
        assert len(result["strength"]["records"]) >= 3
        assert len(result["slump"]["records"]) >= 2

        refreshed = client.get(f"{BASE_URL}/api/projects/{pid}").json()
        assessed = [r for r in refreshed["records"] if r["record"].get("assessment")]
        assert assessed, "analyze did not persist assessments onto stored records"

    def test_import_404_for_unknown_document(self, client, project):
        response = client.post(f"{BASE_URL}/api/projects/{project['id']}/import/{uuid.uuid4()}")
        assert response.status_code == 404


# ---------------- module: sharing ----------------
class TestSharing:
    def test_viewer_share_is_publicly_readable(self, client, project):
        created = client.post(f"{BASE_URL}/api/projects/{project['id']}/shares", json={"permission": "VIEWER"})
        assert created.status_code == 200, created.text
        payload = created.json()
        assert payload["token"] and payload["share_path"] == f"/share/{payload['token']}"
        public = requests.get(f"{BASE_URL}/api/shared/{payload['token']}")
        assert public.status_code == 200, public.text
        body = public.json()
        assert body["permission"] == "VIEWER"
        assert body["project"]["id"] == project["id"]
        assert "members" not in body["project"]
        assert isinstance(body["records"], list)

    def test_invalid_share_token_404(self):
        assert requests.get(f"{BASE_URL}/api/shared/{uuid.uuid4().hex}").status_code == 404


# ---------------- module: upload validation ----------------
class TestUploadValidation:
    def test_unsupported_suffix_rejected(self, client, project):
        response = _upload(client, project["id"], "TEST_bad.csv", b"a,b\n1,2\n", "text/csv")
        assert response.status_code == 400, response.text
        assert "PDF" in response.json().get("detail", "")

    def test_upload_requires_auth(self, project):
        response = requests.post(f"{BASE_URL}/api/projects/{project['id']}/upload",
                                 files={"file": ("TEST_x.xlsx", b"x", XLSX_MIME)})
        assert response.status_code == 401

    @pytest.mark.slow
    def test_oversized_file_rejected(self, client, project):
        payload = b"0" * (104857600 + 1024)
        codes = []
        # Retry once: the ingress intermittently converts the early 413 close into a 502.
        for _ in range(2):
            try:
                response = _upload(client, project["id"], "TEST_big.xlsx", payload)
            except requests.RequestException as exc:
                codes.append(f"transport-error:{exc}")
                continue
            codes.append(response.status_code)
            if response.status_code == 413:
                return
        pytest.fail(f"Oversized upload never returned 413; observed {codes}")


# ---------------- module: OCR (scanned PDF) ----------------
def _scanned_pdf() -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    rows = [
        ["Kode", "Tanggal Uji", "Umur", "Kuat Tekan MPa"],
        ["OCR-01", "08/01/2026", "7", "21.5"],
        ["OCR-02", "29/01/2026", "28", "32.4"],
        ["OCR-03", "30/01/2026", "28", "33.6"],
    ]
    columns = [80, 620, 1150, 1500]
    image = Image.new("RGB", (2100, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 52)
    for row_index, row in enumerate(rows):
        y = 80 + row_index * 130
        for column_index, cell in enumerate(row):
            draw.text((columns[column_index], y), cell, fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=200.0)
    return buf.getvalue()


class TestOcrPdf:
    @pytest.mark.slow
    def test_scanned_pdf_ocr_detects_records(self, client, project):
        doc = _upload(client, project["id"], "TEST_scanned.pdf", _scanned_pdf(), "application/pdf").json()
        status = _wait(client, project["id"], doc["id"], attempts=90, delay=1.0)
        assert status["status"] == "completed", status.get("error")
        extraction = status["extraction"]
        assert extraction["tables"], f"no table detected; warnings={extraction.get('warnings')}"
        methods = {t["records"][0]["source"]["method"] for t in extraction["tables"] if t["records"]}
        assert "pdf-ocr" in methods, methods
        assert extraction["detected"] >= 2, extraction["detected"]
