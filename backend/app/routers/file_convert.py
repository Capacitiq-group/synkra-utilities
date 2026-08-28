"""
File Converter — Section 12.
Implemented: PDF -> images (zip), CSV -> XLSX.
DOCX -> PDF is gated behind ENABLE_DOCX_TO_PDF — see docs/API.md for why:
it genuinely needs LibreOffice ("soffice"), which is a ~300MB dependency
that doesn't belong on the same lightweight host as everything else here.
Deploy it as a separate optional worker if/when you need it.
"""
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import (
    ALLOWED_CSV_MIME,
    ALLOWED_DOC_MIME,
    ENABLE_DOCX_TO_PDF,
    MAX_UPLOAD_BYTES,
    RATE_LIMIT_HEAVY,
)
from app.core.cleanup import cleanup_task, new_job_dir
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/file/convert", tags=["File Converter"])


@router.post("/pdf-to-images")
@limiter.limit(RATE_LIMIT_HEAVY)
async def pdf_to_images(
    request: Request,
    file: UploadFile,
    dpi: int = Query(150, ge=72, le=300),
):
    data = await read_and_validate_upload(file, {"application/pdf"}, MAX_UPLOAD_BYTES)
    doc = fitz.open(stream=data, filetype="pdf")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix)
            zf.writestr(f"page-{i:03d}.png", pix.tobytes("png"))
    doc.close()
    zip_buf.seek(0)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="pdf-pages.zip"'},
    )


@router.post("/csv-to-xlsx")
@limiter.limit(RATE_LIMIT_HEAVY)
async def csv_to_xlsx(request: Request, file: UploadFile):
    data = await read_and_validate_upload(file, ALLOWED_CSV_MIME, MAX_UPLOAD_BYTES)
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse CSV: {exc}") from exc

    out = io.BytesIO()
    df.to_excel(out, index=False, engine="openpyxl")
    out.seek(0)

    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="converted.xlsx"'},
    )


@router.post("/docx-to-pdf")
@limiter.limit(RATE_LIMIT_HEAVY)
async def docx_to_pdf(request: Request, file: UploadFile):
    if not ENABLE_DOCX_TO_PDF:
        raise HTTPException(
            501,
            "DOCX-to-PDF is disabled on this instance. It requires a LibreOffice "
            "worker — see docs/API.md before enabling.",
        )
    data = await read_and_validate_upload(file, ALLOWED_DOC_MIME, MAX_UPLOAD_BYTES)

    job_dir = new_job_dir()
    src_path = job_dir / "input.docx"
    src_path.write_bytes(data)

    try:
        proc = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(job_dir), str(src_path)],
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise HTTPException(500, "LibreOffice (soffice) is not installed on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Conversion timed out.") from exc

    out_path = job_dir / "input.pdf"
    if proc.returncode != 0 or not out_path.exists():
        raise HTTPException(500, f"Conversion failed: {proc.stderr.decode(errors='ignore')[:500]}")

    return StreamingResponse(
        io.BytesIO(out_path.read_bytes()),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="converted.pdf"'},
        background=cleanup_task(job_dir),
    )
