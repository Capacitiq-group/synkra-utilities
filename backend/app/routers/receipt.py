"""
Receipt Generator — Section 23 of the product spec.
Basic transaction receipt only — explicitly not accounting software.
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

router = APIRouter(prefix="/documents/receipt", tags=["Receipt Generator"])


class ReceiptRequest(BaseModel):
    style: DocumentStyle = DocumentStyle()
    seller: Party
    customer: Party
    receipt_number: str
    transaction_date: str
    items: list[LineItem]
    payment_method: str | None = None
    notes: str | None = None


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def generate_receipt(request: Request, body: ReceiptRequest):
    if not body.items:
        raise HTTPException(400, "At least one line item is required.")

    logo_bytes = await fetch_logo(body.style.logo_url)

    pdf_bytes = build_document_pdf(
        doc_title="RECEIPT",
        doc_number_label="Receipt #",
        doc_number=body.receipt_number,
        date_fields=[("Date", body.transaction_date)],
        left_label="Seller",
        left_party=body.seller,
        right_label="Customer",
        right_party=body.customer,
        items=body.items,
        style=body.style,
        logo_bytes=logo_bytes,
        extra_fields=[("Payment Method", body.payment_method)],
        text_blocks=[("Notes", body.notes)],
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="receipt-{body.receipt_number}.pdf"'},
    )
