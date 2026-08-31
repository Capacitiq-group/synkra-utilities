"""Purchase Order Generator — Section 22 of the product spec."""
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import RATE_LIMIT_DEFAULT
from app.core.documents.logo import fetch_logo
from app.core.documents.pdf import build_document_pdf
from app.core.documents.schemas import DocumentStyle, LineItem, Party
from app.core.ratelimit import limiter

router = APIRouter(prefix="/documents/purchase-order", tags=["Purchase Order Generator"])


class PurchaseOrderRequest(BaseModel):
    style: DocumentStyle = DocumentStyle()
    buyer: Party
    supplier: Party
    po_number: str
    issue_date: str
    delivery_date: str | None = None
    delivery_address: str | None = None
    items: list[LineItem]
    notes: str | None = None


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def generate_purchase_order(request: Request, body: PurchaseOrderRequest):
    if not body.items:
        raise HTTPException(400, "At least one line item is required.")

    logo_bytes = await fetch_logo(body.style.logo_url)

    date_fields = [("Issued", body.issue_date)]
    if body.delivery_date:
        date_fields.append(("Delivery Date", body.delivery_date))

    pdf_bytes = build_document_pdf(
        doc_title="PURCHASE ORDER",
        doc_number_label="PO #",
        doc_number=body.po_number,
        date_fields=date_fields,
        left_label="Buyer",
        left_party=body.buyer,
        right_label="Supplier",
        right_party=body.supplier,
        items=body.items,
        style=body.style,
        logo_bytes=logo_bytes,
        extra_fields=[("Delivery Address", body.delivery_address)],
        text_blocks=[("Notes", body.notes)],
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="purchase-order-{body.po_number}.pdf"'},
    )
