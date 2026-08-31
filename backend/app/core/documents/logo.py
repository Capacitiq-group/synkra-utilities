"""Tiny shared helper so each document router doesn't repeat the same
try/except around safe_fetch_bytes."""
from fastapi import HTTPException

from app.core.safe_fetch import UnsafeUrlError, safe_fetch_bytes

LOGO_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


async def fetch_logo(logo_url: str | None) -> bytes | None:
    if not logo_url:
        return None
    try:
        raw, _content_type = await safe_fetch_bytes(logo_url, LOGO_ALLOWED_CONTENT_TYPES)
        return raw
    except UnsafeUrlError as e:
        raise HTTPException(400, f"Could not use logo_url: {e}") from e
    except Exception as e:
        raise HTTPException(400, f"Could not fetch logo_url: {e}") from e
