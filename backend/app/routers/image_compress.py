"""Image Compressor — Section 13. No account, no storage, no dashboard."""
import io

from fastapi import APIRouter, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from app.config import ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES, RATE_LIMIT_DEFAULT
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/image/compress", tags=["Image Compressor"])


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def compress_image(
    request: Request,
    file: UploadFile,
    quality: int = Query(75, ge=1, le=95, description="Lower = smaller file, more artifacts."),
):
    data = await read_and_validate_upload(file, ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES)
    original_size = len(data)

    img = Image.open(io.BytesIO(data))
    fmt = (img.format or "JPEG").upper()
    fmt = "JPEG" if fmt == "JPG" else fmt

    out = io.BytesIO()
    save_kwargs = {"optimize": True}
    if fmt in ("JPEG",):
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = quality
    elif fmt == "WEBP":
        save_kwargs["quality"] = quality
    elif fmt == "PNG":
        # PNG is lossless; "quality" maps to compress_level (0-9).
        save_kwargs["compress_level"] = max(1, min(9, round(9 - (quality / 100) * 8)))
    else:
        fmt = "JPEG"
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = quality

    img.save(out, format=fmt, **save_kwargs)
    out.seek(0)
    compressed_size = out.getbuffer().nbytes
    saved_pct = round((1 - compressed_size / original_size) * 100, 1) if original_size else 0

    return StreamingResponse(
        out,
        media_type=f"image/{fmt.lower()}",
        headers={
            "Content-Disposition": f'attachment; filename="compressed.{fmt.lower()}"',
            "X-Original-Size-Bytes": str(original_size),
            "X-Compressed-Size-Bytes": str(compressed_size),
            "X-Size-Saved-Percent": str(saved_pct),
            "Access-Control-Expose-Headers": "X-Original-Size-Bytes,X-Compressed-Size-Bytes,X-Size-Saved-Percent",
        },
    )
