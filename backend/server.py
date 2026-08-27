"""CQAS API: authentication, projects, records, uploads, analysis, and reports."""
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import io
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import bcrypt
import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from analysis import analyze
from extraction import extract_document

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Concrete Quality Assessment System")
api = APIRouter(prefix="/api")
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 104857600
JWT_ALGORITHM = "HS256"

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

def now(): return datetime.now(timezone.utc).isoformat()
def oid(value): return str(value) if isinstance(value, ObjectId) else value
def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def verify_password(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())
def token(user_id): return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=12), "type": "access"}, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)

async def current_user(request: Request):
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw: raise HTTPException(401, "Not authenticated")
    try: payload = jwt.decode(raw, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError: raise HTTPException(401, "Invalid or expired session")
    # Users use application-level UUIDs so records remain portable across MongoDB instances.
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user: raise HTTPException(401, "User not found")
    user["id"] = user.get("id") or oid(user.get("_id")); user.pop("_id", None); return user

async def project_access(project_id: str, user: dict = Depends(current_user)):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project: raise HTTPException(404, "Project not found")
    member = next((m for m in project.get("members", []) if m["user_id"] == user["id"]), None)
    if not member: raise HTTPException(403, "You do not have access to this project")
    return project, member["role"], user

@api.get("/")
async def root(): return {"message": "Concrete Quality Assessment System API"}

@api.post("/auth/register")
async def register(body: Credentials, request: Request):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "An account with this email already exists")
    user = {"id": str(uuid.uuid4()), "email": email, "name": body.name or email.split("@")[0], "password_hash": hash_password(body.password), "created_at": now()}
    await db.users.insert_one(user.copy())
    response = {k: v for k, v in user.items() if k != "password_hash"}
    return _auth_response(response, token(user["id"]))

@api.post("/auth/login")
async def login(body: Credentials, request: Request):
    identifier = body.email.lower().strip()
    attempt = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if attempt and attempt.get("locked_until", "") > now():
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": identifier})
    if not user or not verify_password(body.password, user["password_hash"]):
        failures = (attempt or {}).get("failures", 0) + 1
        update = {"identifier": identifier, "failures": failures, "updated_at": now()}
        if failures >= 5: update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(401, "Email or password is incorrect")
    await db.login_attempts.delete_one({"identifier": identifier})
    safe = {k: oid(v) for k, v in user.items() if k not in {"password_hash", "_id"}}
    return _auth_response(safe, token(user["id"]))

def _auth_response(data, jwt_token):
    from fastapi.responses import JSONResponse
    response = JSONResponse(data); response.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=43200, path="/"); return response

@api.post("/auth/logout")
async def logout():
    from fastapi.responses import JSONResponse
    response = JSONResponse({"ok": True}); response.delete_cookie("access_token", path="/"); return response

@api.get("/auth/me")
async def me(user=Depends(current_user)): return user

@api.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    projects = await db.projects.find({"members.user_id": user["id"]}, {"_id": 0}).to_list(100)
    project_ids = [p["id"] for p in projects]
    records = await db.records.find({"project_id": {"$in": project_ids}}, {"_id": 0}).to_list(5000) if project_ids else []
    counts = {"projects": len(projects), "documents": await db.documents.count_documents({"project_id": {"$in": project_ids}}) if project_ids else 0, "slump": sum(r["test_type"] == "slump" for r in records), "strength": sum(r["test_type"] == "strength" for r in records)}
    statuses = {s: sum(r.get("record", {}).get("assessment", {}).get("status") == s for r in records) for s in ("COMPLIANT", "WARNING", "NON-COMPLIANT", "INSUFFICIENT DATA")}
    return {"counts": counts, "statuses": statuses, "projects": projects}

@api.get("/projects")
async def list_projects(user=Depends(current_user)):
    return await db.projects.find({"members.user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)

@api.post("/projects")
async def create_project(body: ProjectIn, user=Depends(current_user)):
    project = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": now(), "members": [{"user_id": user["id"], "role": "OWNER", "email": user["email"]}], "settings": {"min_slump": None, "max_slump": None, "target_slump": None, "design_strength": None, "slump_unit": "mm", "strength_unit": "MPa"}}
    await db.projects.insert_one(project.copy()); return project

@api.get("/projects/{project_id}")
async def get_project(project_id: str, access=Depends(project_access)):
    project, role, _ = access
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    docs = await db.documents.find({"project_id": project_id}, {"_id": 0}).to_list(100)
    return {**project, "role": role, "records": records, "documents": docs}

@api.post("/projects/{project_id}/records")
async def add_record(project_id: str, body: RecordIn, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER": raise HTTPException(403, "Viewer access cannot edit records")
    item = {"id": str(uuid.uuid4()), "project_id": project_id, "test_type": body.test_type, "record": body.record, "created_at": now()}
    await db.records.insert_one(item.copy()); return item

@api.post("/projects/{project_id}/analyze")
async def run_analysis(project_id: str, access=Depends(project_access)):
    project, role, _ = access
    if role == "VIEWER": raise HTTPException(403, "Viewer access cannot analyze records")
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    grouped = {"slump": [r["record"] for r in records if r["test_type"] == "slump"], "strength": [r["record"] for r in records if r["test_type"] == "strength"]}
    output = {key: analyze(value, key, project.get("settings", {})) for key, value in grouped.items()}
    await db.analysis.update_one({"project_id": project_id}, {"$set": {"project_id": project_id, "result": output, "updated_at": now()}}, upsert=True)
    return output

@api.post("/projects/{project_id}/upload")
async def upload(project_id: str, file: UploadFile = File(...), access=Depends(project_access)):
    _, role, user = access
    if role == "VIEWER": raise HTTPException(403, "Viewer access cannot upload documents")
    if Path(file.filename or "").suffix.lower() not in {".pdf", ".xlsx", ".xls"}: raise HTTPException(400, "Only PDF, XLSX, and XLS files are supported")
    data = await file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE: raise HTTPException(413, "File exceeds the 100 MB limit.")
    document_id = str(uuid.uuid4()); destination = UPLOAD_DIR / f"{document_id}_{Path(file.filename).name}"; destination.write_bytes(data)
    try: extraction = extract_document(data, file.filename)
    except Exception as exc: raise HTTPException(422, f"Unable to detect a structured table: {exc}")
    doc = {"id": document_id, "project_id": project_id, "filename": file.filename, "size": len(data), "path": str(destination), "uploaded_by": user["id"], "created_at": now(), "extraction": extraction}
    await db.documents.insert_one(doc.copy()); return {k: v for k, v in doc.items() if k != "path"}

@api.post("/projects/{project_id}/import/{document_id}")
async def finalize_import(project_id: str, document_id: str, access=Depends(project_access)):
    _, role, _ = access
    if role == "VIEWER": raise HTTPException(403, "Viewer access cannot import records")
    document = await db.documents.find_one({"id": document_id, "project_id": project_id}, {"_id": 0})
    if not document: raise HTTPException(404, "Document not found")
    inserted = 0
    for record in document["extraction"]["records"]:
        test_type = "slump" if any(key in record for key in ("actual_slump", "target_slump")) else "strength"
        await db.records.insert_one({"id": str(uuid.uuid4()), "project_id": project_id, "document_id": document_id, "test_type": test_type, "record": record, "created_at": now()}); inserted += 1
    return {"inserted": inserted}

@api.get("/projects/{project_id}/report")
async def report(project_id: str, access=Depends(project_access)):
    project, _, _ = access
    records = await db.records.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    buffer = io.BytesIO(); pdf = canvas.Canvas(buffer, pagesize=A4); pdf.setTitle("Concrete Quality Assessment Report")
    pdf.setFillColorRGB(0.85, 0.35, 0.02); pdf.setFont("Helvetica-Bold", 20); pdf.drawString(48, 790, "CONCRETE QUALITY ASSESSMENT REPORT")
    pdf.setFillColorRGB(0.08, 0.1, 0.14); pdf.setFont("Helvetica", 11); y = 755
    for line in [f"Project: {project['name']} ({project.get('code', '')})", f"Generated: {datetime.now().strftime('%d %B %Y')}", f"Records: {len(records)}", "", "This report is a decision-support tool and does not replace laboratory testing or professional engineering judgment."]:
        pdf.drawString(48, y, line); y -= 20
    for record in records[:24]:
        row = record["record"]; label = row.get("sample_code") or row.get("record_number") or "Unidentified"; value = row.get("compressive_strength") or row.get("actual_slump") or "—"; unit = "MPa" if record["test_type"] == "strength" else "mm"; pdf.drawString(60, y, f"{label}: {value} {unit} | {row.get('assessment', {}).get('status', 'UNASSESSED')}"); y -= 15
        if y < 60: pdf.showPage(); y = 790
    pdf.setFont("Helvetica-Oblique", 8); pdf.drawString(48, 30, "Concrete Quality Assessment System | Developed by Nathan | D4 Civil Engineering")
    pdf.save(); buffer.seek(0); return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=concrete-quality-report.pdf"})

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[os.environ["FRONTEND_ORIGIN"]], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    if not await db.users.find_one({"email": os.environ["ADMIN_EMAIL"].lower()}):
        await db.users.insert_one({"id": str(uuid.uuid4()), "email": os.environ["ADMIN_EMAIL"].lower(), "name": "CQAS Admin", "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]), "created_at": now()})
    if not await db.projects.find_one({"code": "NBS-DEMO"}):
        admin = await db.users.find_one({"email": os.environ["ADMIN_EMAIL"].lower()}, {"_id": 0})
        project = {"id": str(uuid.uuid4()), "name": "Navapark Business Suites — DEMO DATA", "code": "NBS-DEMO", "location": "Bandung", "description": "Clearly labeled sample project for evaluation.", "created_at": now(), "members": [{"user_id": admin["id"], "role": "OWNER", "email": admin["email"]}], "settings": {"min_slump": 90, "max_slump": 120, "target_slump": 100, "design_strength": 30, "slump_unit": "mm", "strength_unit": "MPa"}}
        await db.projects.insert_one(project)
        samples = [{"sample_code": "C-001", "test_date": "2026-01-08", "casting_date": "2026-01-01", "age_days": 7, "compressive_strength": 27.4, "planned_strength": 30, "notes": "DEMO DATA"}, {"sample_code": "C-002", "test_date": "2026-01-29", "casting_date": "2026-01-01", "age_days": 28, "compressive_strength": 34.2, "planned_strength": 30, "notes": "DEMO DATA"}]
        for sample in samples: await db.records.insert_one({"id": str(uuid.uuid4()), "project_id": project["id"], "test_type": "strength", "record": sample, "created_at": now()})

@app.on_event("shutdown")
async def shutdown(): client.close()