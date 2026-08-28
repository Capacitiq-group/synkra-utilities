"""
Central configuration. Everything here is read from environment variables
so the same image can be deployed to staging/prod without code changes.
"""
import os
from pathlib import Path

# --- General ---
APP_NAME = "Synkra Business Utilities API"
API_PREFIX = "/api/v1"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "https://synkra.co.za").split(",") if o.strip()]

# --- Storage (temporary only — nothing here is ever persisted) ---
TEMP_DIR = Path(os.getenv("SYNKRA_TEMP_DIR", "/tmp/synkra-utilities"))
TEMP_FILE_TTL_SECONDS = int(os.getenv("SYNKRA_TEMP_TTL", "600"))  # 10 min, then hard-deleted

# --- Size / abuse limits (Section 31 of the product spec) ---
MAX_UPLOAD_BYTES = int(os.getenv("SYNKRA_MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_IMAGE_BYTES = int(os.getenv("SYNKRA_MAX_IMAGE_MB", "15")) * 1024 * 1024
MAX_CSV_BYTES = int(os.getenv("SYNKRA_MAX_CSV_MB", "10")) * 1024 * 1024

# Anonymous rate limits — per IP, enforced by slowapi.
# Tune per-endpoint in the router if a tool needs a different ceiling.
RATE_LIMIT_DEFAULT = os.getenv("SYNKRA_RATE_LIMIT", "20/hour")
RATE_LIMIT_HEAVY = os.getenv("SYNKRA_RATE_LIMIT_HEAVY", "10/hour")  # bg-remove, file-convert

# --- Allowed file types (Section 30 — never trust extension alone) ---
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOC_MIME = {"application/pdf",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ALLOWED_CSV_MIME = {"text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"}

BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".scr", ".sh", ".ps1", ".msi",
    ".jar", ".vbs", ".zip", ".rar", ".7z", ".js", ".py", ".php",
}

# Feature flag: DOCX -> PDF needs a LibreOffice ("soffice") binary on the host.
# That's a genuinely heavy dependency (300MB+), which conflicts with the
# "keep it lightweight" requirement — see docs/API.md for the tradeoff.
# Deploy it as a separate optional worker/container; leave this False on
# the lightweight API host unless soffice is actually installed there.
ENABLE_DOCX_TO_PDF = os.getenv("SYNKRA_ENABLE_DOCX_TO_PDF", "false").lower() == "true"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
