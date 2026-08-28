"""
Background Remover — Section 15.
Uses rembg (self-hosted, ONNX-based U2Net) — no per-image API cost,
matching the spec's "prefer self-hosted" instruction.

Note: rembg downloads its model (~176MB) to the container on first run
and caches it. Bake the model into the Docker image at build time
(see Dockerfile) so the first real user request isn't the one paying
for a slow cold-start download.
"""
import io

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import StreamingResponse
from rembg import remove

from app.config import ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES, RATE_LIMIT_HEAVY
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/image/remove-background", tags=["Background Remover"])


@router.post("")
@limiter.limit(RATE_LIMIT_HEAVY)
async def remove_background(request: Request, file: UploadFile):
    data = await read_and_validate_upload(file, ALLOWED_IMAGE_MIME, MAX_IMAGE_BYTES)
    result_bytes = remove(data)  # returns PNG bytes with alpha channel

    return StreamingResponse(
        io.BytesIO(result_bytes),
        media_type="image/png",
        headers={"Content-Disposition": 'attachment; filename="no-background.png"'},
    )
