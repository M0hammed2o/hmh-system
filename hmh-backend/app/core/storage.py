"""
Persistent file storage helper.

Uses Supabase Storage when SUPABASE_URL and SUPABASE_SERVICE_KEY are set.
Falls back to local disk (UPLOAD_DIR) when they are not — local disk is a
development/test convenience only; see private-storage rules below.

Two Supabase buckets are used, for different privacy guarantees:

  - `_BUCKET` (public, "hmh-uploads"): legacy upload paths that predate the
    2026-08-03 evidence-privacy hardening (delivery notes/signatures, stock
    usage evidence, milestone stage photos, generated MR/PO PDFs). Unchanged
    by this module — callers that need this get it by leaving `private=False`
    (the default).
  - `_PRIVATE_BUCKET` (private, "hmh-evidence-private" by default): the
    generic Attachment-table upload path (`attachment_service.save_attachment`,
    used by Fuel evidence and the `/attachments/upload` endpoint). Objects
    here are never returned as permanent public URLs — only short-lived
    signed URLs via `create_signed_url()`, generated on demand by the
    permission-checked `/attachments/{id}/download` endpoint.

Usage:
    from app.core.storage import save_upload

    path = save_upload(content_bytes, "attachments/FUEL_ISSUE/<id>/abc.jpg", private=True)
    # Returns "supabase://<path>" (private) or "/uploads/..." (local) —
    # never a directly fetchable URL for private uploads.
"""

import os
import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import StorageError

logger = logging.getLogger(__name__)

_BUCKET = "hmh-uploads"


def _supabase_enabled() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _private_bucket() -> str:
    return settings.SUPABASE_PRIVATE_BUCKET


def _local_fallback_allowed() -> bool:
    """Local disk may only be used outside production-like environments.

    Production must not silently lose evidence to Render's ephemeral disk,
    nor serve it unauthenticated via the /uploads static mount.
    """
    return settings.APP_ENV.strip().lower() in {"development", "dev", "test", "testing", "local"}


def storage_mode() -> str:
    """Return 'supabase' or 'local_disk' — used in startup logs and health checks."""
    return "supabase" if _supabase_enabled() else "local_disk"


def verify_supabase_connection() -> dict:
    """
    Try a lightweight Supabase Storage API call to confirm the legacy public
    bucket is reachable. Returns {"ok": True/False, "mode": ..., "error": str|None}.
    """
    if not _supabase_enabled():
        return {"ok": False, "mode": "local_disk", "error": "SUPABASE_URL or SUPABASE_SERVICE_KEY not set — using local disk (photos lost on Render restart)"}
    try:
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
                    "error": f"Bucket '{_BUCKET}' not found. Create it in Supabase Dashboard → Storage → New Bucket (name: hmh-uploads, public: true)."}
        return {"ok": False, "mode": "supabase", "error": f"Supabase returned HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as exc:
        return {"ok": False, "mode": "supabase", "error": str(exc)}


def verify_private_storage() -> dict:
    """
    Check that the private evidence bucket is configured, reachable, and
    actually marked private on Supabase. Used by the admin storage-status
    endpoint and intended for a future production preflight check.
    """
    bucket = _private_bucket()
    if not _supabase_enabled():
        return {"ok": False, "bucket": bucket,
                "error": "SUPABASE_URL or SUPABASE_SERVICE_KEY not set — Fuel evidence and attachment "
                         "uploads will fail outside development/test."}
    try:
        url = f"{settings.SUPABASE_URL}/storage/v1/bucket/{bucket}"
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
            timeout=10,
        )
        if resp.status_code == 404:
            return {"ok": False, "bucket": bucket,
                    "error": f"Private bucket '{bucket}' not found. Create it in Supabase Dashboard → "
                             f"Storage → New Bucket (public: FALSE)."}
        if resp.status_code not in (200, 206):
            return {"ok": False, "bucket": bucket, "error": f"Supabase returned HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        if data.get("public") is True:
            return {"ok": False, "bucket": bucket,
                    "error": f"Bucket '{bucket}' is public. It must be private — Fuel evidence and "
                             f"attachments must never be reachable without a signed URL."}
        return {"ok": True, "bucket": bucket, "error": None}
    except Exception as exc:
        return {"ok": False, "bucket": bucket, "error": str(exc)}


def save_upload(content: bytes, relative_path: str, private: bool = False) -> str:
    """
    Save bytes to storage and return a stored-path reference.

    relative_path: e.g. "attachments/FUEL_ISSUE/<id>/abc.jpg"
    private: True for Fuel evidence and generic Attachment-table uploads —
        routes through the private bucket and never returns a directly
        fetchable URL. False (default) preserves the legacy public-bucket
        behaviour for callers that predate this hardening.

    Returns:
      private=True:  "supabase://<relative_path>" (Supabase) or "/uploads/..." (local, dev/test only)
      private=False: Supabase public URL, or "/uploads/..." (local)

    Raises StorageError if private=True, Supabase is unavailable, and local
    fallback is not allowed (i.e. outside development/test) — the caller
    must not silently persist evidence to ephemeral, unauthenticated local
    disk in production.
    """
    if _supabase_enabled():
        return _save_to_supabase(content, relative_path, private=private)
    if private and not _local_fallback_allowed():
        raise StorageError(
            "Persistent private evidence storage (Supabase) is not configured. "
            "Refusing to write evidence to local disk outside development/test."
        )
    return _save_to_disk(content, relative_path)


def delete_upload(stored_path: str) -> bool:
    """Best-effort compensating delete for a previously staged upload."""
    if not stored_path:
        return True
    if stored_path.startswith("/uploads/"):
        relative = stored_path[len("/uploads/"):].replace("/", os.sep)
        root = os.path.realpath(settings.UPLOAD_DIR)
        target = os.path.realpath(os.path.join(root, relative))
        if os.path.commonpath([root, target]) != root:
            logger.error("Refusing to delete upload outside UPLOAD_DIR: %s", stored_path)
            return False
        try:
            if os.path.exists(target):
                os.remove(target)
            return True
        except OSError:
            logger.exception("Could not remove staged local upload: %s", target)
            return False
    if stored_path.startswith("supabase://"):
        if not _supabase_enabled():
            logger.warning("No Supabase configuration to clean up private object: %s", stored_path)
            return False
        relative = stored_path[len("supabase://"):]
        url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{_private_bucket()}/{relative}"
        try:
            response = httpx.delete(url, headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"}, timeout=15)
            if response.status_code in (200, 204, 404):
                return True
            logger.error("Supabase private object delete returned %s for %s", response.status_code, relative)
        except Exception:
            logger.exception("Could not remove staged private Supabase upload: %s", relative)
        return False
    public_prefix = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{_BUCKET}/"
    if _supabase_enabled() and stored_path.startswith(public_prefix):
        relative = stored_path[len(public_prefix):]
        url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{_BUCKET}/{relative}"
        try:
            response = httpx.delete(url, headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"}, timeout=15)
            if response.status_code in (200, 204, 404):
                return True
            logger.error("Supabase staged upload delete returned %s for %s", response.status_code, relative)
        except Exception:
            logger.exception("Could not remove staged Supabase upload: %s", relative)
        return False
    logger.warning("No supported cleanup strategy for staged upload: %s", stored_path)
    return False


def create_signed_url(stored_path: str, expires_in: Optional[int] = None) -> str:
    """
    Generate a short-lived signed URL for a private-bucket object.

    Only valid for "supabase://..." stored paths (private uploads). Raises
    StorageError if Supabase is not configured or the signing call fails.
    """
    if not stored_path.startswith("supabase://"):
        raise ValueError("create_signed_url only supports private 'supabase://' stored paths")
    if not _supabase_enabled():
        raise StorageError("Private evidence storage is not configured.")
    key = stored_path[len("supabase://"):]
    ttl = expires_in or settings.EVIDENCE_SIGNED_URL_EXPIRY_SECONDS
    url = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{_private_bucket()}/{key}"
    try:
        resp = httpx.post(
            url,
            json={"expiresIn": ttl},
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        signed_path = data.get("signedURL") or data.get("signedUrl")
        if not signed_path:
            raise StorageError("Supabase did not return a signed URL for this evidence file.")
        return f"{settings.SUPABASE_URL}/storage/v1{signed_path}"
    except StorageError:
        raise
    except Exception as exc:
        logger.error("Supabase signed URL generation failed for %s: %s", key, exc)
        raise StorageError("Could not generate a temporary evidence access link. Please retry.") from exc


# ── Supabase Storage ──────────────────────────────────────────────────────────

def _save_to_supabase(content: bytes, relative_path: str, private: bool = False) -> str:
    """Upload to Supabase Storage. Returns a permanent public URL (legacy,
    private=False) or an internal 'supabase://...' reference (private=True)."""
    bucket = _private_bucket() if private else _BUCKET
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{relative_path}"
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": _mime_from_path(relative_path),
        "x-upsert": "true",  # overwrite if exists
    }
    try:
        resp = httpx.put(url, content=content, headers=headers, timeout=30)
        resp.raise_for_status()
        if private:
            logger.info("Uploaded to private Supabase Storage: %s", relative_path)
            return f"supabase://{relative_path}"
        public = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{relative_path}"
        logger.info("Uploaded to Supabase Storage: %s", public)
        return public
    except Exception as exc:
        if private:
            if _local_fallback_allowed():
                logger.error("Private evidence upload to Supabase failed: %s — falling back to disk (development only)", exc)
                return _save_to_disk(content, relative_path)
            logger.error("Private evidence upload to Supabase failed: %s", exc)
            raise StorageError("Evidence upload to persistent storage failed. No file was recorded.") from exc
        logger.error("Supabase Storage upload failed: %s — falling back to disk", exc)
        return _save_to_disk(content, relative_path)


# ── Local disk fallback (development/test only for private uploads) ───────────

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
