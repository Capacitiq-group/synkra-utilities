"""Image Converter — Section 14. JPG <-> PNG <-> WEBP."""
import io
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from app.config import ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES, RATE_LIMIT_DEFAULT
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/image/convert", tags=["Image Converter"])


class TargetFormat(str, Enum):
    jpg = "jpg"
    png = "png"
    webp = "webp"


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def convert_image(
    request: Request,
    file: UploadFile,
    target_format: TargetFormat = Query(...),
):
    data = await read_and_validate_upload(file, ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES)
    img = Image.open(io.BytesIO(data))

    fmt = target_format.value.upper()
    fmt = "JPEG" if fmt == "JPG" else fmt

    if fmt == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    out = io.BytesIO()
    try:
        img.save(out, format=fmt)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(400, f"Could not convert image: {exc}") from exc
    out.seek(0)

    return StreamingResponse(
        out,
        media_type=f"image/{fmt.lower()}",
        headers={"Content-Disposition": f'attachment; filename="converted.{target_format.value}"'},
    )
