"""Quotation Generator — Section 21 of the product spec."""
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import RATE_LIMIT_DEFAULT
from app.core.documents.logo import fetch_logo
from app.core.documents.pdf import build_document_pdf
from app.core.documents.schemas import DocumentStyle, LineItem, Party
from app.core.ratelimit import limiter

router = APIRouter(prefix="/documents/quotation", tags=["Quotation Generator"])


class QuotationRequest(BaseModel):
    style: DocumentStyle = DocumentStyle()
    business: Party
    customer: Party
    quote_number: str
    issue_date: str
    valid_until: str | None = None
    items: list[LineItem]
    terms: str | None = None
    notes: str | None = None


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def generate_quotation(request: Request, body: QuotationRequest):
    if not body.items:
        raise HTTPException(400, "At least one line item is required.")

    logo_bytes = await fetch_logo(body.style.logo_url)

    date_fields = [("Issued", body.issue_date)]
    if body.valid_until:
        date_fields.append(("Valid Until", body.valid_until))

    pdf_bytes = build_document_pdf(
        doc_title="QUOTATION",
        doc_number_label="Quote #",
        doc_number=body.quote_number,
        date_fields=date_fields,
        left_label="From",
        left_party=body.business,
        right_label="Quote For",
        right_party=body.customer,
        items=body.items,
        style=body.style,
        logo_bytes=logo_bytes,
        text_blocks=[
            ("Terms & Conditions", body.terms),
            ("Notes", body.notes),
        ],
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="quotation-{body.quote_number}.pdf"'},
    )
