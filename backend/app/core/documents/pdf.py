"""
One renderer, four document types. Invoice/Quotation/PurchaseOrder/Receipt
routers each collect their own fields and call build_document_pdf() with
document-specific labels — the actual layout/drawing code lives here once.
"""
import io

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .calc import compute_line, compute_totals
from .schemas import DocumentStyle, LineItem, Party
from .templates import PRESETS


def _hex(c: str) -> colors.Color:
    return colors.HexColor(c if c.startswith("#") else f"#{c}")


def _safe_logo_reader(logo_bytes: bytes | None) -> ImageReader | None:
    if not logo_bytes:
        return None
    try:
        pil = PILImage.open(io.BytesIO(logo_bytes)).convert("RGBA")
        pil.thumbnail((300, 300))
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        # A bad/corrupt logo image should degrade to "no logo", never fail the whole document.
        return None


def build_document_pdf(
    *,
    doc_title: str,
    doc_number_label: str,
    doc_number: str,
    date_fields: list[tuple[str, str]],
    left_label: str,
    left_party: Party,
    right_label: str,
    right_party: Party,
    items: list[LineItem],
    style: DocumentStyle,
    logo_bytes: bytes | None = None,
    extra_fields: list[tuple[str, str]] | None = None,
    text_blocks: list[tuple[str, str | None]] | None = None,
) -> bytes:
    preset = PRESETS[style.template.value]
    accent = _hex(style.accent_color)
    currency = style.currency_symbol
    logo_img = _safe_logo_reader(logo_bytes)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=(32 if preset.header_style in ("band", "sidebar") else 22) * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    def draw_header(canvas, _doc):
        canvas.saveState()
        width, height = A4

        if preset.header_style == "band":
            canvas.setFillColor(accent)
            canvas.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
            title_color = colors.white
        elif preset.header_style == "sidebar":
            canvas.setFillColor(accent)
            canvas.rect(0, height - 30 * mm, 6 * mm, 30 * mm, fill=1, stroke=0)
            title_color = colors.black
        else:
            title_color = colors.black

        canvas.setFillColor(title_color)
        canvas.setFont(preset.font_bold, 20)
        canvas.drawRightString(width - 18 * mm, height - 18 * mm, doc_title)
        canvas.setFont(preset.font, 9)
        canvas.drawRightString(width - 18 * mm, height - 24 * mm, f"{doc_number_label}: {doc_number}")

        if preset.header_style == "underline":
            canvas.setStrokeColor(accent)
            canvas.setLineWidth(1.5)
            canvas.line(18 * mm, height - 26 * mm, width - 18 * mm, height - 26 * mm)

        if logo_img is not None:
            try:
                canvas.drawImage(
                    logo_img, 18 * mm, height - 26 * mm,
                    width=30 * mm, height=16 * mm,
                    preserveAspectRatio=True, mask="auto", anchor="sw",
                )
            except Exception:
                pass

        canvas.setFont(preset.font, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(width / 2, 10 * mm, "Created with Synkra — synkra.co.za")
        canvas.linkURL(
            "https://synkra.co.za",
            (width / 2 - 30 * mm, 8 * mm, width / 2 + 30 * mm, 12 * mm),
            relative=0,
        )
        canvas.restoreState()

    style_normal = ParagraphStyle("normal", fontName=preset.font, fontSize=preset.base_font_size,
                                   leading=preset.base_font_size * 1.35, alignment=TA_LEFT)
    style_bold = ParagraphStyle("bold", fontName=preset.font_bold, fontSize=preset.base_font_size,
                                 leading=preset.base_font_size * 1.35, alignment=TA_LEFT)

    def party_paragraph(label: str, party: Party) -> Paragraph:
        lines = [f"<b>{label}</b>", party.name]
        if party.address:
            lines.append(party.address.replace("\n", "<br/>"))
        if party.email:
            lines.append(party.email)
        if party.phone:
            lines.append(party.phone)
        if party.tax_number:
            lines.append(f"Tax/Reg: {party.tax_number}")
        return Paragraph("<br/>".join(lines), style_normal)

    story = [Spacer(1, 4)]

    parties_table = Table(
        [[party_paragraph(left_label, left_party), party_paragraph(right_label, right_party)]],
        colWidths=[85 * mm, 85 * mm],
    )
    parties_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(parties_table)
    story.append(Spacer(1, 6))

    if date_fields:
        date_text = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(f"<b>{l}:</b> {v}" for l, v in date_fields)
        story.append(Paragraph(date_text, style_normal))
        story.append(Spacer(1, 8))

    header_row = ["Description", "Qty", f"Unit ({currency})", "Disc %", "Tax %", f"Total ({currency})"]
    rows = [header_row]
    for item in items:
        lt = compute_line(item)
        rows.append([
            item.description,
            f"{item.quantity:g}",
            f"{item.unit_price:,.2f}",
            f"{item.discount_pct:g}",
            f"{item.tax_pct:g}",
            f"{lt.line_total:,.2f}",
        ])

    items_table = Table(rows, colWidths=[65 * mm, 15 * mm, 25 * mm, 18 * mm, 15 * mm, 27 * mm], repeatRows=1)

    if preset.table_style == "grid":
        table_cmds = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    elif preset.table_style == "zebra":
        table_cmds = [
            ("LINEBELOW", (0, 0), (-1, 0), 1, accent),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), accent),
        ]
        for i in range(2, len(rows), 2):
            table_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.Color(0.96, 0.96, 0.96)))
    else:  # minimal
        table_cmds = [
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
        ]

    table_cmds += [
        ("FONTNAME", (0, 0), (-1, 0), preset.font_bold),
        ("FONTNAME", (0, 1), (-1, -1), preset.font),
        ("FONTSIZE", (0, 0), (-1, -1), preset.base_font_size),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    items_table.setStyle(TableStyle(table_cmds))
    story.append(items_table)
    story.append(Spacer(1, 8))

    totals = compute_totals(items)
    totals_rows = [["Subtotal", f"{currency} {totals.subtotal:,.2f}"]]
    if totals.discount_total:
        totals_rows.append(["Discount", f"- {currency} {totals.discount_total:,.2f}"])
    if totals.tax_total:
        totals_rows.append(["Tax", f"{currency} {totals.tax_total:,.2f}"])
    totals_rows.append(["Total", f"{currency} {totals.grand_total:,.2f}"])

    totals_table = Table(totals_rows, colWidths=[30 * mm, 38 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), preset.font),
        ("FONTNAME", (0, -1), (-1, -1), preset.font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), preset.base_font_size + 1),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(totals_table)

    if extra_fields:
        story.append(Spacer(1, 10))
        for label, value in extra_fields:
            if value:
                story.append(Paragraph(f"<b>{label}:</b> {value}", style_normal))
                story.append(Spacer(1, 2))

    if text_blocks:
        for label, content in text_blocks:
            if not content:
                continue
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"<b>{label}</b>", style_bold))
            story.append(Paragraph(content.replace("\n", "<br/>"), style_normal))

    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
    buf.seek(0)
    return buf.getvalue()
