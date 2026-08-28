"""
Email Signature Generator — Section 18.
No account, no storage (unless the caller saves the returned HTML
themselves), no dashboard. Pure template rendering, no file I/O at all —
this is the lightest endpoint in the whole service.
"""
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import RATE_LIMIT_DEFAULT
from app.core.ratelimit import limiter

router = APIRouter(prefix="/email-signature", tags=["Email Signature Generator"])


class SignatureRequest(BaseModel):
    name: str
    job_title: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    logo_url: str | None = None
    linkedin_url: str | None = None
    accent_color: str = "#1a1a2e"


def _row(label_html: str) -> str:
    return f'<tr><td style="padding:2px 0;">{label_html}</td></tr>'


@router.post("/generate", response_class=HTMLResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
def generate_signature(request: Request, body: SignatureRequest):
    e = escape
    accent = body.accent_color if body.accent_color.startswith("#") else f"#{body.accent_color}"

    logo_cell = (
        f'<td style="padding-right:16px;vertical-align:top;">'
        f'<img src="{e(body.logo_url)}" alt="{e(body.company or body.name)}" '
        f'style="max-width:90px;max-height:90px;display:block;"/></td>'
        if body.logo_url
        else ""
    )

    rows = [f'<strong style="color:{accent};font-size:15px;">{e(body.name)}</strong>']
    if body.job_title or body.company:
        line = " — ".join(x for x in [body.job_title, body.company] if x)
        rows.append(f'<span style="color:#555;">{e(line)}</span>')
    contact_bits = []
    if body.phone:
        contact_bits.append(f"📞 {e(body.phone)}")
    if body.email:
        contact_bits.append(f'✉️ <a href="mailto:{e(body.email)}" style="color:{accent};text-decoration:none;">{e(body.email)}</a>')
    if body.website:
        contact_bits.append(f'🌐 <a href="{e(body.website)}" style="color:{accent};text-decoration:none;">{e(body.website)}</a>')
    if contact_bits:
        rows.append(" &nbsp;|&nbsp; ".join(contact_bits))
    if body.linkedin_url:
        rows.append(f'<a href="{e(body.linkedin_url)}" style="color:{accent};text-decoration:none;">LinkedIn</a>')

    rows_html = "".join(_row(r) for r in rows)

    html = f"""<table cellpadding="0" cellspacing="0" style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#222;">
  <tr>
    {logo_cell}
    <td style="vertical-align:top;border-left:3px solid {accent};padding-left:14px;">
      <table cellpadding="0" cellspacing="0">{rows_html}</table>
    </td>
  </tr>
  <tr>
    <td colspan="2" style="padding-top:10px;font-size:10px;color:#999;">
      Signature created with <a href="https://synkra.co.za" style="color:#999;">Synkra</a>
    </td>
  </tr>
</table>"""

    return HTMLResponse(content=html)
