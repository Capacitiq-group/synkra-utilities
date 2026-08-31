"""
Invoice Generator — Section 20 of the product spec.
Basic (anonymous, one-off) generation: no account, no persistent storage.
Not accounting software — this produces a document, nothing is recorded.
"""
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import RATE_LIMIT_DEFAULT
from app.core.documents.logo import fetch_logo
from app.core.documents.pdf import build_document_pdf
from app.core.documents.schemas import DocumentStyle, LineItem, Party
from app.core.ratelimit import limiter

router = APIRouter(prefix="/documents/invoice", tags=["Invoice Generator"])


class InvoiceRequest(BaseModel):
    style: DocumentStyle = DocumentStyle()
    business: Party
    customer: Party
    invoice_number: str
    issue_date: str
    due_date: str | None = None
    items: list[LineItem]
    payment_instructions: str | None = None
    notes: str | None = None


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def generate_invoice(request: Request, body: InvoiceRequest):
    if not body.items:
        raise HTTPException(400, "At least one line item is required.")

    logo_bytes = await fetch_logo(body.style.logo_url)

    date_fields = [("Issued", body.issue_date)]
    if body.due_date:
        date_fields.append(("Due", body.due_date))

    pdf_bytes = build_document_pdf(
        doc_title="INVOICE",
        doc_number_label="Invoice #",
        doc_number=body.invoice_number,
        date_fields=date_fields,
        left_label="From",
        left_party=body.business,
        right_label="Bill To",
        right_party=body.customer,
        items=body.items,
        style=body.style,
        logo_bytes=logo_bytes,
        text_blocks=[
            ("Payment Instructions", body.payment_instructions),
            ("Notes", body.notes),
        ],
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{body.invoice_number}.pdf"'},
    )
