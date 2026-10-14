"""
Content verification and optional malware scanning for uploaded documents.

Two layers, deliberately separate:

  * `verify_declared_type` always runs. It reads the file's own magic bytes
    and refuses anything whose real format does not match the Content-Type
    the client declared. MIME is client-supplied and trivially spoofed, so a
    renamed executable claiming `application/pdf` gets past the existing
    extension and MIME checks — this is what stops it. No external service
    is involved, so it cannot be switched off by a misconfiguration.

  * `scan_for_malware` runs only when a scanner is configured. HMH has no
    scanner today, so this is the integration point rather than an
    implementation: point `AI_IMPORT_SCAN_URL` at a service that accepts the
    bytes and answers whether they are infected (ClamAV REST, a cloud AV
    endpoint, whatever is procured).

When scanning is enabled but the scanner cannot be reached, the default is to
refuse the upload. An unavailable scanner is not evidence that a file is
clean, and a document import path is not worth leaving open for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class UnsafeUpload(Exception):
    """The file is not what it claims to be, or a scanner rejected it."""


@dataclass(frozen=True)
class ScanResult:
    scanned: bool
    infected: bool
    detail: Optional[str] = None


# ── Content sniffing ──────────────────────────────────────────────────────────

# Leading bytes that identify each format we accept. A file must begin with
# one of the signatures for its declared type.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    # RIFF....WEBP — the size field sits between, so the tail is checked separately.
    "image/webp": (b"RIFF",),
    # HEIC/HEIF carry an ISO-BMFF box; the brand appears at offset 4.
    "image/heic": (b"ftyp",),
    "image/heif": (b"ftyp",),
}

# Signatures that must never appear, whatever the declared type. A document
# import path has no business accepting an executable or an archive.
_FORBIDDEN_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "a Windows executable"),
    (b"\x7fELF", "a Linux executable"),
    (b"\xca\xfe\xba\xbe", "a Java class or Mach-O binary"),
    (b"PK\x03\x04", "a ZIP archive"),
    (b"Rar!\x1a\x07", "a RAR archive"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"#!", "a script"),
)


def _matches_signature(content: bytes, mime: str) -> bool:
    signatures = _SIGNATURES.get(mime)
    if not signatures:
        # An accepted type we have no signature for: do not invent a verdict.
        return True
    if mime == "image/webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if mime in ("image/heic", "image/heif"):
        return content[4:8] == b"ftyp"
    return any(content.startswith(sig) for sig in signatures)


def verify_declared_type(content: bytes, declared_mime: str, file_name: str) -> None:
    """
    Refuse a file whose real format contradicts its declared Content-Type.

    Raises UnsafeUpload. Runs on every upload regardless of configuration.
    """
    if not content:
        raise UnsafeUpload(f"'{file_name}' is empty.")

    for signature, description in _FORBIDDEN_SIGNATURES:
        if content.startswith(signature):
            logger.warning(
                "ai_import rejected upload name=%r declared=%s actual=%s",
                file_name, declared_mime, description,
            )
            raise UnsafeUpload(
                f"'{file_name}' is {description}, whatever its name or content type says. "
                f"Only PDFs and photographs are accepted."
            )

    mime = (declared_mime or "").split(";")[0].strip().lower()
    if not _matches_signature(content, mime):
        logger.warning(
            "ai_import rejected upload name=%r declared=%s: content does not match",
            file_name, mime,
        )
        raise UnsafeUpload(
            f"'{file_name}' does not look like a {mime.split('/')[-1].upper()} file. "
            f"Re-save or re-scan it and try again."
        )


# ── Malware scanning ──────────────────────────────────────────────────────────

def scanning_enabled() -> bool:
    return bool(
        getattr(settings, "AI_IMPORT_SCAN_ENABLED", False)
        and getattr(settings, "AI_IMPORT_SCAN_URL", "")
    )


def scan_for_malware(content: bytes, file_name: str) -> ScanResult:
    """
    Submit the bytes to the configured scanner.

    Returns a ScanResult rather than raising for a clean file. Raises
    UnsafeUpload when the scanner reports an infection, and — unless
    AI_IMPORT_SCAN_FAIL_OPEN is set — also when the scanner cannot be
    reached, because an unreachable scanner proves nothing.
    """
    if not scanning_enabled():
        return ScanResult(scanned=False, infected=False, detail="no scanner configured")

    url = settings.AI_IMPORT_SCAN_URL
    timeout = float(getattr(settings, "AI_IMPORT_SCAN_TIMEOUT_SECONDS", 30.0))
    fail_open = bool(getattr(settings, "AI_IMPORT_SCAN_FAIL_OPEN", False))

    try:
        import httpx

        response = httpx.post(
            url,
            files={"file": (file_name, content)},
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
    except Exception as exc:                        # noqa: BLE001 - any failure is "unknown"
        logger.error("ai_import malware scan failed for %r: %s", file_name, exc)
        if fail_open:
            return ScanResult(
                scanned=False, infected=False,
                detail=f"scanner unavailable, accepted under fail-open policy: {exc}",
            )
        raise UnsafeUpload(
            f"'{file_name}' could not be virus-scanned because the scanner is "
            f"unavailable, so it was not accepted. Try again once scanning is working, "
            f"or set AI_IMPORT_SCAN_FAIL_OPEN if uploads must continue regardless."
        ) from exc

    # Accept the common shapes rather than mandating one scanner's contract.
    infected = bool(
        body.get("infected")
        or body.get("is_infected")
        or (str(body.get("status", "")).lower() in ("infected", "found"))
    )
    detail = body.get("virus") or body.get("detail") or body.get("status")

    if infected:
        logger.warning("ai_import malware scan flagged %r: %s", file_name, detail)
        raise UnsafeUpload(
            f"'{file_name}' was flagged by the virus scanner"
            + (f" ({detail})" if detail else "")
            + " and was not stored."
        )

    return ScanResult(scanned=True, infected=False, detail=str(detail) if detail else None)


def check_upload(content: bytes, declared_mime: str, file_name: str) -> ScanResult:
    """Both layers, in order: what the file is, then whether it is safe."""
    verify_declared_type(content, declared_mime, file_name)
    return scan_for_malware(content, file_name)
