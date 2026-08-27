"""CQAS API: authentication (email/password + Google), projects, records, uploads, analysis, reports."""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import io
import logging
import os
import secrets
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any

import bcrypt
import jwt
import requests
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from analysis import analyze
from extraction import apply_mapping_overrides, extract_document, FIELD_SYNONYMS
from reports import build_report
from storage import build_path, get_object, init_storage, put_object

logger = logging.getLogger(__name__)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Concrete Quality Assessment System")
api = APIRouter(prefix="/api")
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 104857600
JWT_ALGORITHM = "HS256"
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class Credentials(BaseModel):
    email: str
    password: str
    name: str = ""


class ProjectIn(BaseModel):
    name: str
    code: str = ""
    location: str = ""
    description: str = ""
    contractor: str = ""
    consultant: str = ""
    owner_name: str = ""


class RecordIn(BaseModel):
    test_type: str
    record: dict[str, Any]


class ShareIn(BaseModel):
    permission: str = "VIEWER"
    expires_at: str | None = None


class MappingOverrideIn(BaseModel):
    overrides: list[dict[str, Any]] = []


class SettingsIn(BaseModel):
    target_slump: float | None = None
    min_slump: float | None = None
    max_slump: float | None = None
    design_strength: float | None = None
    slump_unit: str = "mm"
    strength_unit: str = "MPa"
    area_unit: str = "cm2"
    load_unit: str = "kN"


class TemplateIn(BaseModel):
    name: str
    signature: list[str]
    mappings: dict[str, str] = {}
    test_type: str = "strength"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(value: Any) -> Any:
    return str(value) if isinstance(value, ObjectId) else value


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def make_token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=12), "type": "access"},
        os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM,
    )


async def _resolve_user(request: Request) -> dict | None:
    """Prefer local JWT cookie/header; fall back to Emergent Google session cookie."""
    jwt_raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if jwt_raw:
        try:
            payload = jwt.decode(jwt_raw, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
            if user:
                return user
        except jwt.InvalidTokenError:
            pass
    session_token = request.cookies.get("session_token")
    if session_token:
        session = await db.sessions.find_one({"session_token": session_token}, {"_id": 0})
        if session:
            expires = session.get("expires_at")
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            if expires and expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if not expires or expires > datetime.now(timezone.utc):
                user = await db.users.find_one({"id": session["user_id"]}, {"_id": 0, "password_hash": 0})
                if user:
                    return user
    return None


async def current_user(request: Request) -> dict:
    user = await _resolve_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    user["id"] = user.get("id") or oid(user.get("_id"))
    user.pop("_id", None)
    return user


async def project_access(project_id: str, user: dict = Depends(current_user)):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")
    member = next((m for m in project.get("members", []) if m["user_id"] == user["id"]), None)
    if not member:
        raise HTTPException(403, "You do not have access to this project")
    return project, member["role"], user


@api.get("/")
async def root():
    return {"message": "Concrete Quality Assessment System API"}


@api.get("/config/field-synonyms")
async def field_synonyms():
    """Frontend uses this to power the manual mapping dropdown."""
    return {"fields": list(FIELD_SYNONYMS.keys()), "synonyms": FIELD_SYNONYMS}


def _auth_response(data: dict, jwt_token: str) -> JSONResponse:
    response = JSONResponse(data)
    response.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=43200, path="/")
    return response


@api.post("/auth/register")
async def register(body: Credentials):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists")
    user = {"id": str(uuid.uuid4()), "email": email, "name": body.name or email.split("@")[0], "password_hash": hash_password(body.password), "created_at": now(), "provider": "password"}
    await db.users.insert_one(user.copy())
    response = {k: v for k, v in user.items() if k != "password_hash"}
    return _auth_response(response, make_token(user["id"]))


@api.post("/auth/login")
async def login(body: Credentials):
    identifier = body.email.lower().strip()
    attempt = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if attempt and attempt.get("locked_until", "") > now():
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": identifier})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        failures = (attempt or {}).get("failures", 0) + 1
        update = {"identifier": identifier, "failures": failures, "updated_at": now()}
        if failures >= 5:
            update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(401, "Email or password is incorrect")
    await db.login_attempts.delete_one({"identifier": identifier})
    safe = {k: oid(v) for k, v in user.items() if k not in {"password_hash", "_id"}}
    return _auth_response(safe, make_token(user["id"]))


@api.post("/auth/google/session")
async def google_session(request: Request):
    """Exchange the session_id issued by Emergent Google auth for a persistent httpOnly cookie."""
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        try:
            body = await request.json()
            session_id = body.get("session_id")
        except Exception:
            session_id = None
    if not session_id:
        raise HTTPException(400, "Missing session identifier")
    try:
        emergent = requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id}, timeout=15)
        emergent.raise_for_status()
    except requests.RequestException:
        raise HTTPException(401, "Google session could not be verified")
    profile = emergent.json()
    email = str(profile.get("email", "")).lower().strip()
    if not email:
        raise HTTPException(400, "Google profile is missing an email address")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = {"id": str(uuid.uuid4()), "email": email, "name": profile.get("name") or email.split("@")[0], "picture": profile.get("picture"), "created_at": now(), "provider": "google"}
        await db.users.insert_one(user.copy())
    session_token = profile.get("session_token") or secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.sessions.insert_one({"session_token": session_token, "user_id": user["id"], "expires_at": expires_at.isoformat(), "created_at": now()})
    response_body = {k: v for k, v in user.items() if k != "password_hash"}
    response = JSONResponse(response_body)
    response.set_cookie("session_token", session_token, httponly=True, samesite="none", secure=True, max_age=7 * 24 * 3600, path="/")
    return response


@api.post("/auth/logout")
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.sessions.delete_one({"session_token": session_token})
    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return response


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return user


@api.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    projects = await db.projects.find({"members.user_id": user["id"]}, {"_id": 0}).to_list(100)
    project_ids = [p["id"] for p in projects]
    records = await db.records.find({"project_id": {"$in": project_ids}}, {"_id": 0}).to_list(5000) if project_ids else []
    counts = {
        "projects": len(projects),
        "documents": await db.documents.count_documents({"project_id": {"$in": project_ids}}) if project_ids else 0,
        "slump": sum(r["test_type"] == "slump" for r in records),
        "strength": sum(r["test_type"] == "strength" for r in records),
    }
    statuses = {s: sum(r.get("record", {}).get("assessment", {}).get("status") == s for r in records) for s in ("COMPLIANT", "WARNING", "NON-COMPLIANT", "INSUFFICIENT DATA")}
    return {"counts": counts, "statuses": statuses, "projects": projects}


@api.get("/projects")
async def list_projects(user=Depends(current_user)):
    return await db.projects.find({"members.user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api.post("/projects")
async def create_project(body: ProjectIn, user=Depends(current_user)):
    project = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": now(), "members": [{"user_id": user["id"], "role": "OWNER", "email": user["email"]}], "settings": {"min_slump": None, "max_slump": None, "target_slump": None, "design_strength": None, "slump_unit": "mm", "strength_unit": "MPa"}}
    await db.projects.insert_one(project.copy())
    return project


@api.get("/projects/{project_id}")
async def get_project(project_id: str, access=Depends(project_access)):
    project, role, _ = access
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    docs = await db.documents.find({"project_id": project_id}, {"_id": 0, "storage_path": 0, "path": 0}).to_list(100)
    return {**project, "role": role, "records": records, "documents": docs}


@api.post("/projects/{project_id}/records")
async def add_record(project_id: str, body: RecordIn, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot edit records")
    item = {"id": str(uuid.uuid4()), "project_id": project_id, "test_type": body.test_type, "record": body.record, "created_at": now()}
    await db.records.insert_one(item.copy())
    return item


@api.post("/projects/{project_id}/analyze")
async def run_analysis(project_id: str, access=Depends(project_access)):
    project, role, _ = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot analyze records")
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    grouped = {
        "slump": [r["record"] for r in records if r["test_type"] == "slump"],
        "strength": [r["record"] for r in records if r["test_type"] == "strength"],
    }
    output = {key: analyze(value, key, project.get("settings", {})) for key, value in grouped.items()}
    for record, updated in zip((r for r in records if r["test_type"] == "slump"), output["slump"]["records"]):
        await db.records.update_one({"id": record["id"]}, {"$set": {"record": updated}})
    for record, updated in zip((r for r in records if r["test_type"] == "strength"), output["strength"]["records"]):
        await db.records.update_one({"id": record["id"]}, {"$set": {"record": updated}})
    await db.analysis.update_one({"project_id": project_id}, {"$set": {"project_id": project_id, "result": output, "updated_at": now()}}, upsert=True)
    return output


def share_digest(token_value: str) -> str:
    return hashlib.sha256(token_value.encode()).hexdigest()


async def share_context(token_value: str):
    link = await db.share_links.find_one({"token_hash": share_digest(token_value), "disabled": {"$ne": True}}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Share link is invalid or disabled")
    if link.get("expires_at") and link["expires_at"] <= now():
        raise HTTPException(410, "Share link has expired")
    return link


@api.post("/projects/{project_id}/shares")
async def create_share(project_id: str, body: ShareIn, access=Depends(project_access)):
    project, role, user = access
    if role != "OWNER":
        raise HTTPException(403, "Only the project owner can manage share links")
    if body.permission not in {"VIEWER", "EDITOR"}:
        raise HTTPException(400, "Permission must be VIEWER or EDITOR")
    raw_token = secrets.token_urlsafe(32)
    link = {"id": str(uuid.uuid4()), "project_id": project_id, "token_hash": share_digest(raw_token), "permission": body.permission, "expires_at": body.expires_at, "created_by": user["id"], "created_at": now(), "disabled": False}
    await db.share_links.insert_one(link.copy())
    return {"id": link["id"], "permission": link["permission"], "expires_at": link["expires_at"], "token": raw_token, "share_path": f"/share/{raw_token}"}


@api.get("/projects/{project_id}/shares")
async def list_shares(project_id: str, access=Depends(project_access)):
    _, role, _ = access
    if role != "OWNER":
        raise HTTPException(403, "Only the project owner can view share links")
    return await db.share_links.find({"project_id": project_id}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(50)


@api.delete("/projects/{project_id}/shares/{share_id}")
async def disable_share(project_id: str, share_id: str, access=Depends(project_access)):
    _, role, _ = access
    if role != "OWNER":
        raise HTTPException(403, "Only the project owner can disable share links")
    await db.share_links.update_one({"id": share_id, "project_id": project_id}, {"$set": {"disabled": True, "disabled_at": now()}})
    return {"ok": True}


@api.get("/shared/{raw_token}")
async def get_shared_project(raw_token: str):
    link = await share_context(raw_token)
    project = await db.projects.find_one({"id": link["project_id"]}, {"_id": 0, "members": 0})
    records = await db.records.find({"project_id": link["project_id"]}, {"_id": 0}).to_list(5000)
    return {"project": project, "records": records, "permission": link["permission"], "expires_at": link.get("expires_at")}


@api.get("/projects/{project_id}/insights")
async def project_insights(project_id: str, status: str | None = Query(None), age: int | None = Query(None), supplier: str | None = Query(None), location: str | None = Query(None), date_from: str | None = Query(None), date_to: str | None = Query(None), access=Depends(project_access)):
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    filtered = []
    for item in records:
        row = item.get("record", {})
        assessment = row.get("assessment", {})
        if status and assessment.get("status") != status:
            continue
        if age is not None and row.get("age_days") != age:
            continue
        if supplier and str(row.get("supplier", "")).lower() != supplier.lower():
            continue
        if location and str(row.get("location", row.get("element", ""))).lower() != location.lower():
            continue
        test_date = row.get("test_date") or row.get("date")
        if date_from and (not test_date or test_date < date_from):
            continue
        if date_to and (not test_date or test_date > date_to):
            continue
        filtered.append(item)
    strength = [{"age": r["record"].get("age_days"), "actual": r["record"].get("compressive_strength") or r["record"].get("derived_strength"), "planned": r["record"].get("planned_strength"), "sample": r["record"].get("sample_code")} for r in filtered if r["test_type"] == "strength" and r["record"].get("age_days") is not None]
    slump = [{"date": r["record"].get("test_date") or r["record"].get("date"), "actual": r["record"].get("actual_slump"), "target": r["record"].get("target_slump")} for r in filtered if r["test_type"] == "slump"]
    supplier_totals: dict[str, dict[str, Any]] = {}
    for item in filtered:
        name = item["record"].get("supplier") or "Unspecified"
        bucket = supplier_totals.setdefault(name, {"supplier": name, "records": 0, "compliant": 0, "warning": 0, "non_compliant": 0})
        bucket["records"] += 1
        state = item["record"].get("assessment", {}).get("status", "UNASSESSED").lower().replace("-", "_")
        if state in bucket:
            bucket[state] += 1
    anomalies = []
    for item in filtered:
        for warning in item["record"].get("warnings", []):
            if isinstance(warning, dict):
                anomalies.append({"type": "VERIFICATION", **warning, "date": item["record"].get("test_date")})
            else:
                anomalies.append({"type": "VERIFICATION", "code": None, "params": {}, "message": str(warning), "date": item["record"].get("test_date")})
    return {"filters": {"status": status, "age": age, "supplier": supplier, "location": location, "date_from": date_from, "date_to": date_to}, "total": len(filtered), "strength_by_age": strength, "slump_by_date": slump, "supplier_comparison": list(supplier_totals.values()), "anomaly_trends": anomalies, "summary": {"headline": f"{len(filtered)} records in the current view", "recommendation": "Verify flagged records against source documents, dates, curing records, and applicable project criteria."}}


async def _apply_user_templates(document_id: str, user_id: str, extraction: dict) -> dict:
    """Auto-map a table using saved templates when its header signature matches."""
    tables = extraction.get("tables") or []
    if not tables:
        return extraction
    templates = await db.mapping_templates.find({"user_id": user_id}, {"_id": 0}).to_list(200)
    if not templates:
        return extraction
    template_by_sig = {t["signature"]: t for t in templates}
    overrides: list[dict[str, Any]] = []
    matched: list[str] = []
    for table in tables:
        signature = _template_signature(table.get("source_headers", []))
        template = template_by_sig.get(signature)
        if not template:
            continue
        matched.append(template["name"])
        overrides.append({"table_index": table["table_index"], "test_type": template.get("test_type") or table["test_type"]})
        header_index = {(header or "").strip().lower(): index for index, header in enumerate(table.get("source_headers", []))}
        for header, field in (template.get("mappings") or {}).items():
            key = (header or "").strip().lower()
            if key in header_index:
                overrides.append({"table_index": table["table_index"], "column_index": header_index[key], "field": field})
    if not overrides:
        return extraction
    updated = apply_mapping_overrides(extraction, overrides)
    updated["applied_templates"] = matched
    return updated


async def process_document(project_id: str, document_id: str, storage_path: str, filename: str, user_id: str):
    """Background worker: fetches from cloud storage and runs the full extraction pipeline."""
    await db.documents.update_one({"id": document_id}, {"$set": {"status": "processing", "progress": 20}})
    try:
        data, _ = get_object(storage_path)
        await db.documents.update_one({"id": document_id}, {"$set": {"progress": 55}})
        extraction = extract_document(data, filename)
        extraction = await _apply_user_templates(document_id, user_id, extraction)
        await db.documents.update_one({"id": document_id}, {"$set": {"status": "completed", "progress": 100, "extraction": extraction, "processed_at": now()}})
    except Exception as exc:
        logger.exception("Document processing failed")
        await db.documents.update_one({"id": document_id}, {"$set": {"status": "failed", "progress": 100, "error": str(exc)}})


@api.post("/projects/{project_id}/upload")
async def upload(project_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...), access=Depends(project_access)):
    _, role, user = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot upload documents")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".xlsx", ".xls"}:
        raise HTTPException(400, "Only PDF, XLSX, and XLS files are supported")
    data = await file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "File exceeds the 100 MB limit.")
    document_id = str(uuid.uuid4())
    storage_path = build_path(user["id"], file.filename or f"{document_id}{suffix}")
    stored_locally = False
    try:
        put_object(storage_path, data, file.content_type or "application/octet-stream")
    except Exception as exc:
        logger.warning("Cloud storage upload failed, falling back to local disk: %s", exc)
        destination = UPLOAD_DIR / f"{document_id}_{Path(file.filename or 'file').name}"
        destination.write_bytes(data)
        storage_path = str(destination)
        stored_locally = True
    doc = {"id": document_id, "project_id": project_id, "filename": file.filename, "size": len(data), "storage_path": storage_path, "storage_backend": "local" if stored_locally else "emergent", "uploaded_by": user["id"], "created_at": now(), "status": "queued", "progress": 0}
    if stored_locally:
        async def _local(project_id_local: str, document_id_local: str, path: str, name: str, uploader: str):
            await db.documents.update_one({"id": document_id_local}, {"$set": {"status": "processing", "progress": 20}})
            try:
                content = Path(path).read_bytes()
                extraction = extract_document(content, name)
                extraction = await _apply_user_templates(document_id_local, uploader, extraction)
                await db.documents.update_one({"id": document_id_local}, {"$set": {"status": "completed", "progress": 100, "extraction": extraction, "processed_at": now()}})
            except Exception as exc:
                logger.exception("Local extraction failed")
                await db.documents.update_one({"id": document_id_local}, {"$set": {"status": "failed", "progress": 100, "error": str(exc)}})
        background_tasks.add_task(_local, project_id, document_id, storage_path, file.filename, user["id"])
    else:
        background_tasks.add_task(process_document, project_id, document_id, storage_path, file.filename, user["id"])
    await db.documents.insert_one(doc.copy())
    return {k: v for k, v in doc.items() if k not in {"storage_path"}}


@api.get("/projects/{project_id}/documents/{document_id}/status")
async def document_status(project_id: str, document_id: str, access=Depends(project_access)):
    doc = await db.documents.find_one({"id": document_id, "project_id": project_id}, {"_id": 0, "storage_path": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@api.post("/projects/{project_id}/documents/{document_id}/mapping")
async def override_mapping(project_id: str, document_id: str, body: MappingOverrideIn, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot edit mappings")
    document = await db.documents.find_one({"id": document_id, "project_id": project_id}, {"_id": 0})
    if not document or not document.get("extraction"):
        raise HTTPException(404, "Extraction result not found")
    extraction = apply_mapping_overrides(document["extraction"], body.overrides)
    await db.documents.update_one({"id": document_id}, {"$set": {"extraction": extraction, "mapping_updated_at": now()}})
    return extraction


@api.patch("/projects/{project_id}/settings")
async def update_settings(project_id: str, body: SettingsIn, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot edit settings")
    await db.projects.update_one({"id": project_id}, {"$set": {"settings": body.model_dump(), "settings_updated_at": now()}})
    return body.model_dump()


def _template_signature(headers: list[str]) -> str:
    """Order-independent digest that recognises the same lab report layout."""
    normalized = sorted((h or "").strip().lower() for h in headers if (h or "").strip())
    return hashlib.sha256("||".join(normalized).encode()).hexdigest()


@api.get("/mapping-templates")
async def list_templates(user=Depends(current_user)):
    return await db.mapping_templates.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api.post("/mapping-templates")
async def create_template(body: TemplateIn, user=Depends(current_user)):
    template = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": body.name,
        "signature": _template_signature(body.signature),
        "source_headers": body.signature,
        "mappings": body.mappings,
        "test_type": body.test_type,
        "created_at": now(),
    }
    await db.mapping_templates.insert_one(template.copy())
    return template


@api.delete("/mapping-templates/{template_id}")
async def delete_template(template_id: str, user=Depends(current_user)):
    result = await db.mapping_templates.delete_one({"id": template_id, "user_id": user["id"]})
    if not result.deleted_count:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@api.post("/projects/{project_id}/import/{document_id}")
async def finalize_import(project_id: str, document_id: str, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER":
        raise HTTPException(403, "Viewer access cannot import records")
    document = await db.documents.find_one({"id": document_id, "project_id": project_id}, {"_id": 0})
    if not document:
        raise HTTPException(404, "Document not found")
    inserted = 0
    for record in document.get("extraction", {}).get("records", []):
        assigned = record.get("assigned_test_type")
        if assigned in {"slump", "strength"}:
            test_type = assigned
        else:
            test_type = "slump" if any(key in record for key in ("actual_slump", "target_slump")) else "strength"
        await db.records.insert_one({"id": str(uuid.uuid4()), "project_id": project_id, "document_id": document_id, "test_type": test_type, "record": record, "created_at": now()})
        inserted += 1
    await db.documents.update_one({"id": document_id}, {"$set": {"imported_at": now(), "imported_count": inserted}})
    return {"inserted": inserted}


@api.get("/projects/{project_id}/report")
async def report(project_id: str, lang: str = Query("en"), access=Depends(project_access)):
    project, _, _ = access
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    pdf_bytes = build_report(project, records, lang if lang in {"en", "id"} else "en")
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=concrete-quality-report.pdf"})


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[os.environ["FRONTEND_ORIGIN"]], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.sessions.create_index("session_token", unique=True)
    init_storage()
    if not await db.users.find_one({"email": os.environ["ADMIN_EMAIL"].lower()}):
        await db.users.insert_one({"id": str(uuid.uuid4()), "email": os.environ["ADMIN_EMAIL"].lower(), "name": "CQAS Admin", "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]), "created_at": now(), "provider": "password"})
    if not await db.projects.find_one({"code": "NBS-DEMO"}):
        admin = await db.users.find_one({"email": os.environ["ADMIN_EMAIL"].lower()}, {"_id": 0})
        project = {"id": str(uuid.uuid4()), "name": "Navapark Business Suites — DEMO DATA", "code": "NBS-DEMO", "location": "Bandung", "description": "Clearly labeled sample project for evaluation.", "created_at": now(), "members": [{"user_id": admin["id"], "role": "OWNER", "email": admin["email"]}], "settings": {"min_slump": 90, "max_slump": 120, "target_slump": 100, "design_strength": 30, "slump_unit": "mm", "strength_unit": "MPa"}}
        await db.projects.insert_one(project)
        samples = [
            {"sample_code": "C-001", "test_date": "2026-01-08", "casting_date": "2026-01-01", "age_days": 7, "compressive_strength": 27.4, "planned_strength": 30, "notes": "DEMO DATA"},
            {"sample_code": "C-002", "test_date": "2026-01-29", "casting_date": "2026-01-01", "age_days": 28, "compressive_strength": 34.2, "planned_strength": 30, "notes": "DEMO DATA"},
        ]
        for sample in samples:
            await db.records.insert_one({"id": str(uuid.uuid4()), "project_id": project["id"], "test_type": "strength", "record": sample, "created_at": now()})


@app.on_event("shutdown")
async def shutdown():
    client.close()
