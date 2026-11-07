"""W3C CSS Paged Media (`@page`) and Print Stylesheet Generator for Question Paper Studio."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from src.core.models.enums import Orientation, PageSize
from src.core.models.project_model import LayoutSettings, ProjectState
from src.core.models.template_model import Template

_BASE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
DEFAULT_FONTS_DIR = _BASE_ROOT / "assets" / "fonts"


class CSSGenerator:
    """Generates millimeter-accurate `@page` and document layout CSS for HTML5 preview and vector PDF export."""

    @staticmethod
    def _font_face_declarations(fonts_dir: Optional[Path] = None) -> str:
        """Build `@font-face` declarations pointing to bundled Noto Sans and Noto Sans Devanagari TTF files."""
        fdir = (fonts_dir or DEFAULT_FONTS_DIR).resolve()
        reg_uri = (fdir / "NotoSans-Regular.ttf").as_uri()
        bold_uri = (fdir / "NotoSans-Bold.ttf").as_uri()
        italic_uri = (fdir / "NotoSans-Italic.ttf").as_uri()
        dev_reg_uri = (fdir / "NotoSansDevanagari-Regular.ttf").as_uri()
        dev_bold_uri = (fdir / "NotoSansDevanagari-Bold.ttf").as_uri()

        return f"""
@font-face {{
    font-family: 'Noto Sans';
    src: url('{reg_uri}') format('truetype');
    font-weight: 400;
    font-style: normal;
}}
@font-face {{
    font-family: 'Noto Sans';
    src: url('{bold_uri}') format('truetype');
    font-weight: 700;
    font-style: normal;
}}
@font-face {{
    font-family: 'Noto Sans';
    src: url('{italic_uri}') format('truetype');
    font-weight: 400;
    font-style: italic;
}}
@font-face {{
    font-family: 'Noto Sans Devanagari';
    src: url('{dev_reg_uri}') format('truetype');
    font-weight: 400;
    font-style: normal;
}}
@font-face {{
    font-family: 'Noto Sans Devanagari';
    src: url('{dev_bold_uri}') format('truetype');
    font-weight: 700;
    font-style: normal;
}}
"""

    @staticmethod
    def _page_size_css_value(template: Template) -> str:
        """Return `@page { size: ... }` value in exact millimeters or standard keyword."""
        setup = template.page_setup
        w_mm, h_mm = setup.effective_dimensions_mm
        if setup.size == PageSize.CUSTOM:
            return f"{w_mm:.1f}mm {h_mm:.1f}mm"
        orient = "landscape" if setup.orientation == Orientation.LANDSCAPE else "portrait"
        return f"{setup.size.value} {orient}"

    @staticmethod
    def generate_stylesheet(
        project: ProjectState,
        fonts_dir: Optional[Path] = None,
        preview_sheet_framing: bool = False,
    ) -> str:
        """Generate complete CSS stylesheet for `project`."""
        template = project.template_snapshot
        setup = template.page_setup
        layout: LayoutSettings = project.layout_settings

        w_mm, h_mm = setup.effective_dimensions_mm
        m = setup.margins_mm
        hdr_h = template.header_height_mm
        ftr_h = template.footer_height_mm
        q_space = layout.question_spacing_mm
        base_font = layout.base_font_family or "Noto Sans"
        base_pt = layout.base_font_size_pt
        cols = layout.columns

        page_size_rule = CSSGenerator._page_size_css_value(template)
        font_faces = CSSGenerator._font_face_declarations(fonts_dir=fonts_dir)

        preview_css = ""
        if preview_sheet_framing:
            preview_css = f"""
@media screen {{
    html, body {{
        background-color: #E2E8F0;
        padding: 8mm 0;
    }}
    .paper-document {{
        width: {w_mm:.1f}mm;
        min-height: {h_mm:.1f}mm;
        margin: 0 auto;
        padding: {m.top:.1f}mm {m.right:.1f}mm {m.bottom:.1f}mm {m.left:.1f}mm;
        background: #FFFFFF;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.18);
        box-sizing: border-box;
    }}
}}
"""

        return f"""{font_faces}
@page {{
    size: {page_size_rule};
    margin-top: {m.top:.1f}mm;
    margin-right: {m.right:.1f}mm;
    margin-bottom: {m.bottom:.1f}mm;
    margin-left: {m.left:.1f}mm;
    @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-family: '{base_font}', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
        font-size: 9pt;
    }}
}}

@page :first {{
    margin-top: {m.top:.1f}mm;
    margin-right: {m.right:.1f}mm;
    margin-bottom: {m.bottom:.1f}mm;
    margin-left: {m.left:.1f}mm;
}}

* {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

html, body {{
    margin: 0;
    padding: 0;
    font-family: '{base_font}', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
    font-size: {base_pt:.1f}pt;
    line-height: 1.42;
    color: #0F172A;
}}
{preview_css}

.paper-layout-table {{
    width: 100%;
    border-collapse: collapse;
    border: none;
}}

.paper-header-space {{
    height: {hdr_h:.1f}mm;
    padding: 0;
    border: none;
}}

.paper-footer-space {{
    height: {ftr_h:.1f}mm;
    padding: 0;
    border: none;
}}

.template-header-box {{
    position: relative;
    width: {setup.printable_width_mm:.1f}mm;
    height: {hdr_h:.1f}mm;
    overflow: hidden;
    margin-bottom: 2mm;
}}

.template-footer-box {{
    position: relative;
    width: {setup.printable_width_mm:.1f}mm;
    height: {ftr_h:.1f}mm;
    overflow: hidden;
    margin-top: 2mm;
}}

.canvas-element {{
    position: absolute;
    overflow: hidden;
    font-family: '{base_font}', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
}}

.candidate-info-box {{
    width: 100%;
    border: 1pt solid #1E293B;
    border-collapse: collapse;
    margin-bottom: 3.5mm;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.candidate-info-box td {{
    border: 0.75pt solid #334155;
    padding: 1.8mm 3mm;
    font-size: 9.5pt;
    font-weight: 600;
}}

.general-instructions-box {{
    border: 0.75pt solid #475569;
    background-color: #F8FAFC;
    padding: 2.5mm 3.5mm;
    margin-bottom: 4mm;
    font-size: 9.5pt;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.general-instructions-title {{
    font-weight: 700;
    text-transform: uppercase;
    margin-bottom: 1mm;
    font-size: 10pt;
}}

.watermark-overlay {{
    position: fixed;
    top: 45%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-35deg);
    font-size: 54pt;
    font-weight: 700;
    color: rgba(100, 116, 139, 0.13);
    pointer-events: none;
    z-index: 0;
    white-space: nowrap;
    user-select: none;
}}

.paper-body-columns-1 {{
    column-count: 1;
}}

.paper-body-columns-2 {{
    column-count: 2;
    column-gap: 6mm;
    column-rule: 0.5pt solid #CBD5E1;
}}

.section-container {{
    margin-bottom: 5mm;
}}

.section-container.columns-1 {{
    column-count: 1;
}}

.section-container.columns-2 {{
    column-count: 2;
    column-gap: 6mm;
    column-rule: 0.5pt solid #CBD5E1;
}}

.section-header {{
    text-align: center;
    border-top: 1pt solid #0F172A;
    border-bottom: 1pt solid #0F172A;
    padding: 1.5mm 2mm;
    margin: 3mm 0 3mm 0;
    background-color: #F8FAFC;
    break-after: avoid;
    page-break-after: avoid;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.section-title {{
    font-weight: 700;
    font-size: {base_pt + 1.0:.1f}pt;
    text-transform: uppercase;
    letter-spacing: 0.3pt;
}}

.section-instructions {{
    font-size: {base_pt - 1.0:.1f}pt;
    font-style: italic;
    margin-top: 0.8mm;
}}

.choice-group-banner {{
    font-weight: 700;
    font-style: italic;
    font-size: {base_pt - 0.5:.1f}pt;
    color: #1E293B;
    margin: 2mm 0 1.5mm 0;
    break-after: avoid;
    page-break-after: avoid;
}}

.or-divider {{
    text-align: center;
    font-weight: 700;
    font-size: {base_pt:.1f}pt;
    margin: 1.8mm 0;
    letter-spacing: 1pt;
    break-inside: avoid;
    page-break-inside: avoid;
    break-after: avoid;
    page-break-after: avoid;
}}

.shared-passage-block {{
    border: 0.75pt solid #64748B;
    background-color: #F8FAFC;
    padding: 2.5mm 3.5mm;
    margin-bottom: 2.5mm;
    break-inside: avoid;
    page-break-inside: avoid;
    break-after: avoid;
    page-break-after: avoid;
}}

.shared-passage-instruction {{
    font-weight: 700;
    font-size: {base_pt - 0.5:.1f}pt;
    margin-bottom: 1.2mm;
}}

.question-block {{
    margin-bottom: {q_space:.1f}mm;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.question-block.force-page-break {{
    break-before: page;
    page-break-before: always;
}}

.question-row {{
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    width: 100%;
}}

.question-number {{
    font-weight: 700;
    min-width: 9mm;
    padding-right: 2mm;
    flex-shrink: 0;
}}

.question-content {{
    flex: 1 1 auto;
    min-width: 0;
}}

.question-content p {{
    margin: 0 0 1.2mm 0;
}}

.question-marks-right {{
    font-weight: 700;
    min-width: 14mm;
    text-align: right;
    padding-left: 2.5mm;
    flex-shrink: 0;
    white-space: nowrap;
}}

.question-marks-inline {{
    font-weight: 700;
    margin-left: 2mm;
    white-space: nowrap;
}}

.bilingual-side-by-side {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4mm;
    align-items: start;
}}

.bilingual-sequential .secondary-lang-block {{
    margin-top: 1mm;
    color: #1E293B;
    font-family: 'Noto Sans Devanagari', 'Noto Sans', sans-serif;
}}

.mcq-options-grid-2x2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5mm 4mm;
    margin-top: 1.5mm;
}}

.mcq-options-inline {{
    display: flex;
    flex-wrap: wrap;
    gap: 1.5mm 6mm;
    margin-top: 1.5mm;
}}

.mcq-options-stacked {{
    display: flex;
    flex-direction: column;
    gap: 1.2mm;
    margin-top: 1.5mm;
}}

.mcq-option-item {{
    display: flex;
    align-items: baseline;
    gap: 1.5mm;
}}

.mcq-option-label {{
    font-weight: 700;
}}

.word-bank-box {{
    border: 0.75pt dashed #475569;
    padding: 1.5mm 2.5mm;
    margin-top: 1.5mm;
    font-size: {base_pt - 0.5:.1f}pt;
}}

.match-pair-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 2mm;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.match-pair-table th,
.match-pair-table td {{
    border: 0.75pt solid #1E293B;
    padding: 1.5mm 2.5mm;
    vertical-align: top;
    text-align: left;
}}

.match-pair-table tr {{
    break-inside: avoid;
    page-break-inside: avoid;
}}

.diagram-container {{
    margin: 2mm 0;
    break-inside: avoid;
    page-break-inside: avoid;
}}

.diagram-caption {{
    font-size: {base_pt - 1.5:.1f}pt;
    font-style: italic;
    margin-top: 1mm;
}}

.subquestions-container {{
    margin-left: 7mm;
    margin-top: 1.5mm;
}}

.answer-space-lines {{
    margin-top: 2mm;
}}

.answer-line {{
    border-bottom: 0.6pt dotted #64748B;
    height: 6.5mm;
    width: 100%;
}}

.teacher-key-badge {{
    margin-top: 1.5mm;
    padding: 1.2mm 2.5mm;
    background-color: #ECFDF5;
    border-left: 2.5pt solid #059669;
    color: #065F46;
    font-size: {base_pt - 0.5:.1f}pt;
}}
"""
