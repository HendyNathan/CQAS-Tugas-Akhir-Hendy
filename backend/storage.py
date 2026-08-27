"""Emergent Object Storage wrapper for durable PDF/Excel persistence."""
import logging
import os
import uuid
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = os.environ.get("APP_NAME", "cqas")

_storage_key: str | None = None


def init_storage(force: bool = False) -> str | None:
    """Provision a reusable storage session key. Safe to call multiple times."""
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        logger.warning("EMERGENT_LLM_KEY missing; storage disabled")
        return None
    try:
        response = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        response.raise_for_status()
        _storage_key = response.json()["storage_key"]
        return _storage_key
    except Exception as exc:
        logger.warning("Storage init failed: %s", exc)
        return None


def build_path(user_id: str, filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".") or "bin"
    return f"{APP_NAME}/uploads/{user_id}/{uuid.uuid4().hex}.{ext}"


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage is not initialized")
    response = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=180)
    if response.status_code == 404:
        key = init_storage(force=True)
        response = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=180)
    response.raise_for_status()
    return response.json()


def get_object(path: str) -> tuple[bytes, str]:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage is not initialized")
    response = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=120)
    if response.status_code == 404:
        key = init_storage(force=True)
        response = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=120)
    response.raise_for_status()
    return response.content, response.headers.get("Content-Type", "application/octet-stream")
