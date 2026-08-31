"""
Shared request building blocks for the document generators (Invoice,
Quotation, Purchase Order, Receipt — Sections 20-23 of the product spec).

Each document type has its own router/request model, but they all
compose Party, LineItem, and DocumentStyle from here so the PDF renderer
in pdf.py only needs to know one shape.
"""
from enum import Enum

from pydantic import BaseModel, Field


class DocumentTemplate(str, Enum):
    modern = "modern"      # color band header, zebra-striped table
    classic = "classic"    # serif, underline header, ruled grid table
    minimal = "minimal"    # no header decoration, hairline table
    bold = "bold"          # heavy sidebar accent, bold grid table
    compact = "compact"    # tight spacing, small type — fits more on one page


class Party(BaseModel):
    name: str
    address: str | None = None
    email: str | None = None
    phone: str | None = None
    tax_number: str | None = Field(None, description="VAT number / company registration number.")


class LineItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0
    discount_pct: float = Field(0, ge=0, le=100)
    tax_pct: float = Field(0, ge=0, le=100, description="e.g. 15 for South African VAT.")


class DocumentStyle(BaseModel):
    template: DocumentTemplate = DocumentTemplate.modern
    accent_color: str = "#1a1a2e"
    logo_url: str | None = Field(
        None, description="Publicly reachable image URL — fetched server-side with SSRF guards, not uploaded."
    )
    currency_symbol: str = "R"
