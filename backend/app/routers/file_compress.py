"""
File Compressor — Section 11.
PDF via PyMuPDF (garbage-collect + deflate + image downsampling).
DOCX via re-zipping with recompressed embedded images.
Image files should go through /image/compress instead.
"""
import io
import zipfile

import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from app.config import ALLOWED_DOC_MIME, MAX_UPLOAD_BYTES, RATE_LIMIT_DEFAULT
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/file/compress", tags=["File Compressor"])


def _compress_pdf(data: bytes, image_quality: int) -> bytes:
    doc = fitz.open(stream=data, filetype="pdf")

    # Downsample/recompress embedded images in place.
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                raw = base["image"]
                pil_img = Image.open(io.BytesIO(raw))
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=image_quality, optimize=True)
                if buf.getbuffer().nbytes < len(raw):
                    doc.update_stream(xref, buf.getvalue())
            except Exception:
                # Not every xref is a straightforward raster image (masks,
                # CMYK, etc). Skip anything we can't safely re-encode.
                continue

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()


def _compress_docx(data: bytes) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    out_buf = io.BytesIO()

    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out_zip:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename.startswith("word/media/") and item.filename.lower().endswith(
                (".png", ".jpg", ".jpeg")
            ):
                try:
                    img = Image.open(io.BytesIO(content))
                    fmt = "JPEG" if img.format == "JPEG" else img.format
                    buf = io.BytesIO()
                    if fmt == "JPEG":
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        img.save(buf, format="JPEG", quality=75, optimize=True)
                    else:
                        img.save(buf, format=fmt, optimize=True)
                    if buf.getbuffer().nbytes < len(content):
                        content = buf.getvalue()
                except Exception:
                    pass
            out_zip.writestr(item, content)

    return out_buf.getvalue()


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def compress_file(
    request: Request,
    file: UploadFile,
    image_quality: int = Query(70, ge=1, le=95, description="Applies to PDF/DOCX embedded images."),
):
    data = await read_and_validate_upload(file, ALLOWED_DOC_MIME, MAX_UPLOAD_BYTES)
    original_size = len(data)

    import magic

    detected = magic.from_buffer(data, mime=True)

    if detected == "application/pdf":
        result = _compress_pdf(data, image_quality)
        media_type = "application/pdf"
        filename = "compressed.pdf"
    elif "wordprocessingml" in detected:
        result = _compress_docx(data)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "compressed.docx"
    else:
        raise HTTPException(400, "Only PDF and DOCX are supported here — use /image/compress for images.")

    compressed_size = len(result)
    saved_pct = round((1 - compressed_size / original_size) * 100, 1) if original_size else 0

    return StreamingResponse(
        io.BytesIO(result),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Original-Size-Bytes": str(original_size),
            "X-Compressed-Size-Bytes": str(compressed_size),
            "X-Size-Saved-Percent": str(saved_pct),
            "Access-Control-Expose-Headers": "X-Original-Size-Bytes,X-Compressed-Size-Bytes,X-Size-Saved-Percent",
        },
    )
