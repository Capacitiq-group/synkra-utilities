"""
Five visual presets, applied identically across Invoice/Quotation/PO/
Receipt so "template=bold" looks the same regardless of document type.
Only reportlab's built-in Base-14 fonts are used (Helvetica, Times,
Courier) — no font files to bundle, keeps the image lightweight.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TemplatePreset:
    label: str
    font: str
    font_bold: str
    header_style: str   # "band" | "sidebar" | "underline" | "plain"
    table_style: str    # "grid" | "zebra" | "minimal"
    base_font_size: float


PRESETS: dict[str, TemplatePreset] = {
    "modern": TemplatePreset(
        label="Modern", font="Helvetica", font_bold="Helvetica-Bold",
        header_style="band", table_style="zebra", base_font_size=9,
    ),
    "classic": TemplatePreset(
        label="Classic", font="Times-Roman", font_bold="Times-Bold",
        header_style="underline", table_style="grid", base_font_size=10,
    ),
    "minimal": TemplatePreset(
        label="Minimal", font="Helvetica", font_bold="Helvetica-Bold",
        header_style="plain", table_style="minimal", base_font_size=9,
    ),
    "bold": TemplatePreset(
        label="Bold", font="Helvetica-Bold", font_bold="Helvetica-Bold",
        header_style="sidebar", table_style="grid", base_font_size=10,
    ),
    "compact": TemplatePreset(
        label="Compact", font="Helvetica", font_bold="Helvetica-Bold",
        header_style="plain", table_style="minimal", base_font_size=7.5,
    ),
}
