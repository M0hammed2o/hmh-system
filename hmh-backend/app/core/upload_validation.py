"""
Shared upload validation — MIME type, extension blocklist, and file size checks.

Call validate_upload() before reading file bytes in any upload endpoint.
Raises:
  HTTP 415  if MIME type is not in the allowed set, or if the filename
            extension is on the executable/script blocklist
  HTTP 413  if file exceeds the configured maximum
"""

import os

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

# Photo uploads (field capture, fuel evidence, delivery notes, stage evidence)
PHOTO_MIMES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
})

# Document uploads — photos + PDF (delivery notes, invoices, expense receipts)
DOCUMENT_MIMES: frozenset[str] = PHOTO_MIMES | frozenset({
    "application/pdf",
})

# Spreadsheet/CSV imports (BOQ templates, stock imports)
SPREADSHEET_MIMES: frozenset[str] = frozenset({
    "text/csv",
    "text/plain",               # some OS/browsers report CSV as text/plain
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})

# Extensions that must never be stored regardless of declared MIME type.
# MIME is client-declared and trivially spoofed; the filename extension
# provides a second independent signal for obviously dangerous file types.
BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".msi", ".dll", ".com", ".scr", ".pif",   # Windows executables
    ".bat", ".cmd", ".ps1", ".psm1", ".psd1",          # Windows scripts
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",    # Windows scripting
    ".sh", ".bash", ".zsh", ".fish", ".csh",           # Unix shells
    ".php", ".php3", ".php4", ".php5", ".phtml",       # Server-side web
    ".asp", ".aspx", ".jsp", ".jspx",                  # Server-side web
    ".py", ".rb", ".pl", ".lua",                       # Interpreted scripts
    ".jar", ".war", ".ear",                            # Java archives
    ".apk", ".ipa",                                    # Mobile executables
})


def _check_extension(filename: str | None) -> None:
    """Raise HTTP 415 if the filename has a blocked extension."""
    if not filename:
        return
    ext = os.path.splitext(filename)[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File extension '{ext}' is not permitted.",
        )


def validate_upload(
    file: UploadFile,
    allowed: frozenset[str] = DOCUMENT_MIMES,
    max_mb: int | None = None,
) -> None:
    """
    Validate MIME type, extension blocklist, and file size.

    Checks the client-declared Content-Type header of the multipart part,
    then independently rejects filenames with blocked extensions.
    Raises HTTP 415 for disallowed types, HTTP 413 for oversized files.

    Args:
        file:    The UploadFile from FastAPI.
        allowed: Set of permitted MIME strings.  Defaults to DOCUMENT_MIMES.
        max_mb:  Max megabytes. Defaults to settings.MAX_UPLOAD_SIZE_MB.
    """
    _check_extension(file.filename)

    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if mime not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{mime}' is not allowed. "
                f"Accepted: {', '.join(sorted(allowed))}."
            ),
        )

    limit_bytes = (max_mb or settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > limit_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {size / 1024 / 1024:.1f} MB exceeds the "
                f"{max_mb or settings.MAX_UPLOAD_SIZE_MB} MB limit."
            ),
        )
