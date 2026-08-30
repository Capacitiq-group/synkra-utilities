"""
QR Code Generator — Section 5.1 of the spec.
No account, no storage, no dashboard. Generated and streamed back
immediately as PNG or SVG.

Two additions this round:
- `transparent_background`: the previous version accepted back_color but
  always called .convert("RGB") before saving, which silently discards any
  alpha channel — a transparent PNG was never actually possible even
  though the field suggested it was. Fixed below.
- `logo_url`: embeds a logo/icon fetched from a URL (not an upload — see
  app/core/safe_fetch.py for why fetching arbitrary URLs server-side needs
  SSRF guards) into the center of the QR code, with a white backing plate
  for scan reliability and error_correction auto-bumped to H when a logo
  is present and the caller left error_correction at its default.
"""
import io
from enum import Enum
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field

from app.core.ratelimit import limiter
from app.core.safe_fetch import UnsafeUrlError, safe_fetch_bytes
from app.config import RATE_LIMIT_DEFAULT

router = APIRouter(prefix="/qr", tags=["QR Code Generator"])


class QRType(str, Enum):
    url = "url"
    text = "text"
    email = "email"
    phone = "phone"
    whatsapp = "whatsapp"
    wifi = "wifi"
    vcard = "vcard"


class QROutputFormat(str, Enum):
    png = "png"
    svg = "svg"


class ErrorCorrection(str, Enum):
    low = "L"
    medium = "M"
    quartile = "Q"
    high = "H"


LOGO_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


class QRRequest(BaseModel):
    qr_type: QRType
    output_format: QROutputFormat = QROutputFormat.png
    error_correction: ErrorCorrection = ErrorCorrection.medium
    size: int = Field(10, ge=1, le=40, description="Box size in pixels (PNG only).")
    margin: int = Field(4, ge=0, le=20)
    fill_color: str = "#000000"
    back_color: str = "#FFFFFF"
    transparent_background: bool = Field(
        False, description="PNG only. Ignores back_color and produces an alpha-transparent background."
    )
    logo_url: str | None = Field(
        None,
        description=(
            "PNG only. URL of a logo/icon image (PNG, JPEG, or WebP) to place in the "
            "center of the QR code. Must be publicly reachable - fetched server-side, "
            "not uploaded."
        ),
    )
    logo_size_pct: int = Field(
        22, ge=10, le=35, description="Logo width as a percentage of the QR code's width."
    )

    # Payload fields — required subset depends on qr_type.
    value: str | None = None          # url / text
    email: str | None = None
    email_subject: str | None = None
    email_body: str | None = None
    phone: str | None = None
    whatsapp_number: str | None = None
    whatsapp_message: str | None = None
    wifi_ssid: str | None = None
    wifi_password: str | None = None
    wifi_encryption: str = "WPA"       # WPA | WEP | nopass
    wifi_hidden: bool = False
    vcard_name: str | None = None
    vcard_org: str | None = None
    vcard_title: str | None = None
    vcard_phone: str | None = None
    vcard_email: str | None = None
    vcard_website: str | None = None
    vcard_address: str | None = None


_EC_MAP = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}


def _build_payload(req: QRRequest) -> str:
    t = req.qr_type
    if t in (QRType.url, QRType.text):
        if not req.value:
            raise HTTPException(400, "`value` is required for url/text QR codes.")
        return req.value

    if t == QRType.email:
        if not req.email:
            raise HTTPException(400, "`email` is required for email QR codes.")
        params = []
        if req.email_subject:
            params.append(f"subject={quote(req.email_subject)}")
        if req.email_body:
            params.append(f"body={quote(req.email_body)}")
        query = ("?" + "&".join(params)) if params else ""
        return f"mailto:{req.email}{query}"

    if t == QRType.phone:
        if not req.phone:
            raise HTTPException(400, "`phone` is required for phone QR codes.")
        return f"tel:{req.phone}"

    if t == QRType.whatsapp:
        if not req.whatsapp_number:
            raise HTTPException(400, "`whatsapp_number` is required for whatsapp QR codes.")
        number = req.whatsapp_number.replace("+", "").replace(" ", "")
        text = f"?text={quote(req.whatsapp_message)}" if req.whatsapp_message else ""
        return f"https://wa.me/{number}{text}"

    if t == QRType.wifi:
        if not req.wifi_ssid:
            raise HTTPException(400, "`wifi_ssid` is required for wifi QR codes.")

        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace('"', '\\"')

        enc = req.wifi_encryption.upper()
        pwd = f"P:{esc(req.wifi_password)};" if enc != "NOPASS" and req.wifi_password else ""
        hidden = "H:true;" if req.wifi_hidden else ""
        return f"WIFI:T:{enc};S:{esc(req.wifi_ssid)};{pwd}{hidden};"

    if t == QRType.vcard:
        if not req.vcard_name:
            raise HTTPException(400, "`vcard_name` is required for vCard QR codes.")
        lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:{req.vcard_name}", f"FN:{req.vcard_name}"]
        if req.vcard_org:
            lines.append(f"ORG:{req.vcard_org}")
        if req.vcard_title:
            lines.append(f"TITLE:{req.vcard_title}")
        if req.vcard_phone:
            lines.append(f"TEL:{req.vcard_phone}")
        if req.vcard_email:
            lines.append(f"EMAIL:{req.vcard_email}")
        if req.vcard_website:
            lines.append(f"URL:{req.vcard_website}")
        if req.vcard_address:
            lines.append(f"ADR:;;{req.vcard_address};;;;")
        lines.append("END:VCARD")
        return "\n".join(lines)

    raise HTTPException(400, "Unsupported qr_type.")


async def _apply_logo(img: Image.Image, logo_url: str, size_pct: int) -> Image.Image:
    try:
        raw, _content_type = await safe_fetch_bytes(logo_url, LOGO_ALLOWED_CONTENT_TYPES)
    except UnsafeUrlError as e:
        raise HTTPException(400, f"Could not use logo_url: {e}") from e
    except Exception as e:
        raise HTTPException(400, f"Could not fetch logo_url: {e}") from e

    try:
        logo = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception as e:
        raise HTTPException(400, "logo_url did not point to a readable image.") from e

    base = img.convert("RGBA")
    target_w = int(base.width * (size_pct / 100))
    ratio = target_w / logo.width
    target_h = int(logo.height * ratio)
    logo = logo.resize((max(1, target_w), max(1, target_h)), Image.LANCZOS)

    # White backing plate behind the logo (with a small margin) so the logo
    # doesn't blend into whatever fill/back colors were chosen, and so the
    # QR modules directly under the logo read as consistently "blank"
    # rather than partially colored - both matter for scan reliability.
    pad = max(4, target_w // 12)
    plate_w, plate_h = logo.width + pad * 2, logo.height + pad * 2
    plate = Image.new("RGBA", (plate_w, plate_h), (255, 255, 255, 255))
    plate.paste(logo, (pad, pad), logo)

    pos = ((base.width - plate_w) // 2, (base.height - plate_h) // 2)
    base.alpha_composite(plate, dest=pos)
    return base


@router.post("/generate")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def generate_qr(request: Request, body: QRRequest):
    payload = _build_payload(body)

    if body.logo_url and body.output_format != QROutputFormat.png:
        raise HTTPException(400, "logo_url is only supported for PNG output.")
    if body.transparent_background and body.output_format != QROutputFormat.png:
        raise HTTPException(400, "transparent_background is only supported for PNG output.")

    # A logo covers part of the QR code, so it needs headroom to recover
    # from that when scanning. Auto-bump to H unless the caller explicitly
    # asked for something else.
    error_correction = body.error_correction
    if body.logo_url and error_correction == ErrorCorrection.medium:
        error_correction = ErrorCorrection.high

    qr = qrcode.QRCode(
        error_correction=_EC_MAP[error_correction.value],
        box_size=body.size,
        border=body.margin,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    buf = io.BytesIO()

    if body.output_format == QROutputFormat.svg:
        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory, fill_color=body.fill_color, back_color=body.back_color)
        img.save(buf)
        media_type = "image/svg+xml"
        ext = "svg"
    else:
        back_color = "transparent" if body.transparent_background else body.back_color
        img = qr.make_image(fill_color=body.fill_color, back_color=back_color)
        # Only convert to plain RGB (dropping any alpha channel) when a
        # transparent background was NOT requested. This is the actual fix
        # to the transparency bug - the previous version always converted.
        if not body.transparent_background:
            img = img.convert("RGB")

        if body.logo_url:
            img = await _apply_logo(img, body.logo_url, body.logo_size_pct)

        img.save(buf, format="PNG")
        media_type = "image/png"
        ext = "png"

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="synkra-qr.{ext}"'},
        )
