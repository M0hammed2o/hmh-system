"""
Persistent file storage helper.

Uses Supabase Storage when SUPABASE_URL and SUPABASE_SERVICE_KEY are set.
Falls back to local disk (UPLOAD_DIR) when they are not.

Usage:
    from app.core.storage import save_upload, public_url

    path = save_upload(content_bytes, "fuel_evidence/odometer/abc.jpg")
    # Returns a URL the frontend can use to fetch the file.
"""

import os
import uuid
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BUCKET = "hmh-uploads"


def _supabase_enabled() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def storage_mode() -> str:
    """Return 'supabase' or 'local_disk' — used in startup logs and health checks."""
    return "supabase" if _supabase_enabled() else "local_disk"


def verify_supabase_connection() -> dict:
    """
    Try a lightweight Supabase Storage API call to confirm credentials work.
    Returns {"ok": True/False, "mode": "supabase"/"local_disk", "error": str|None}.
    """
    if not _supabase_enabled():
        return {"ok": False, "mode": "local_disk", "error": "SUPABASE_URL or SUPABASE_SERVICE_KEY not set — using local disk (photos lost on Render restart)"}
    try:
        # List objects in the bucket root — cheap read-only API call
        url = f"{settings.SUPABASE_URL}/storage/v1/bucket/{_BUCKET}"
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
            timeout=10,
        )
        if resp.status_code in (200, 206):
            return {"ok": True, "mode": "supabase", "error": None}
        if resp.status_code == 404:
            return {"ok": False, "mode": "supabase",
                    "error": f"Bucket '{_BUCKET}' not found. Create it in Supabase Dashboard → Storage → New Bucket (name: hmh-uploads, public: true)"}
        return {"ok": False, "mode": "supabase", "error": f"Supabase returned HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"ok": False, "mode": "supabase", "error": str(exc)}


def save_upload(content: bytes, relative_path: str) -> str:
    """
    Save bytes to storage and return the public URL.

    relative_path: e.g. "fuel_evidence/odometer/abc.jpg"

    Returns:
      Supabase public URL if Supabase is configured
      Local path "/uploads/..." otherwise
    """
    if _supabase_enabled():
        return _save_to_supabase(content, relative_path)
    return _save_to_disk(content, relative_path)


def public_url(stored_path: str) -> str:
    """Convert a stored path to a publicly accessible URL."""
    if stored_path.startswith("http"):
        return stored_path  # already absolute
    if _supabase_enabled() and stored_path.startswith("supabase://"):
        key = stored_path[len("supabase://"):]
        return f"{settings.SUPABASE_URL}/storage/v1/object/public/{_BUCKET}/{key}"
    return stored_path  # local /uploads/... path


# ── Supabase Storage ──────────────────────────────────────────────────────────

def _save_to_supabase(content: bytes, relative_path: str) -> str:
    """Upload to Supabase Storage and return a permanent public URL."""
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{_BUCKET}/{relative_path}"
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": _mime_from_path(relative_path),
        "x-upsert": "true",  # overwrite if exists
    }
    try:
        resp = httpx.put(url, content=content, headers=headers, timeout=30)
        resp.raise_for_status()
        public = f"{settings.SUPABASE_URL}/storage/v1/object/public/{_BUCKET}/{relative_path}"
        logger.info("Uploaded to Supabase Storage: %s", public)
        return public
    except Exception as exc:
        logger.error("Supabase Storage upload failed: %s — falling back to disk", exc)
        return _save_to_disk(content, relative_path)


# ── Local disk fallback ───────────────────────────────────────────────────────

def _save_to_disk(content: bytes, relative_path: str) -> str:
    """Save to UPLOAD_DIR and return a /uploads/... relative URL path."""
    full_path = os.path.join(settings.UPLOAD_DIR, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as fh:
        fh.write(content)
    return f"/uploads/{relative_path}"


def _mime_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
