"""
QR Code Generator — Section 5.1 of the spec.
No account, no storage, no dashboard. Generated and streamed back
immediately as PNG or SVG.
"""
import io
from enum import Enum
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.ratelimit import limiter
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


class QRRequest(BaseModel):
    qr_type: QRType
    output_format: QROutputFormat = QROutputFormat.png
    error_correction: ErrorCorrection = ErrorCorrection.medium
    size: int = Field(10, ge=1, le=40, description="Box size in pixels (PNG only).")
    margin: int = Field(4, ge=0, le=20)
    fill_color: str = "#000000"
    back_color: str = "#FFFFFF"

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


@router.post("/generate")
@limiter.limit(RATE_LIMIT_DEFAULT)
def generate_qr(request: Request, body: QRRequest):
    payload = _build_payload(body)

    qr = qrcode.QRCode(
        error_correction=_EC_MAP[body.error_correction.value],
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
        img = qr.make_image(fill_color=body.fill_color, back_color=body.back_color).convert("RGB")
        img.save(buf, format="PNG")
        media_type = "image/png"
        ext = "png"

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="synkra-qr.{ext}"'},
    )
