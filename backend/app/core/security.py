"""
Implements the "Validate" step of the file lifecycle:
Receive -> Validate -> Quarantine -> Process -> Return -> Delete

Never trust a file's declared extension or Content-Type. We check the
actual magic bytes of the content and cross-check against an allowlist.
"""
from pathlib import Path

import magic
from fastapi import HTTPException, UploadFile

from app.config import BLOCKED_EXTENSIONS, MAX_UPLOAD_BYTES

# Magic-byte signatures we accept, keyed by the MIME python-magic reports.
_SAFE_MIME_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "text/csv": {".csv"},
    "text/plain": {".csv", ".txt"},  # some CSV exports report as plain text
}


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


async def read_and_validate_upload(
    file: UploadFile,
    allowed_mimes: set[str],
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> bytes:
    """
    Reads the upload fully into memory (files are size-capped, so this is
    fine) and validates it before any processing touches it. Raises
    HTTPException on anything suspicious.
    """
    ext = _extension(file.filename)
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is not allowed.")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            413, f"File exceeds the {max_bytes // (1024 * 1024)}MB limit for this tool."
        )

    # Magic-byte sniff — this is the real check, not the extension.
    detected_mime = magic.from_buffer(data, mime=True)
    if detected_mime not in allowed_mimes:
        raise HTTPException(
            400,
            f"File content ({detected_mime}) doesn't match an accepted type for this tool.",
        )

    valid_exts = _SAFE_MIME_EXTENSIONS.get(detected_mime, set())
    if valid_exts and ext and ext not in valid_exts:
        # Extension actively lies about the content — reject rather than guess.
        raise HTTPException(400, "File extension does not match file content.")

    return data
