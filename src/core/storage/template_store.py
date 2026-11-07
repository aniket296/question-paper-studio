"""Local Template Store: Built-in default templates, CRUD operations, and DOCX/PDF template importer."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import docx
from pypdf import PdfReader

from src.core.models.enums import (
    CanvasElementType,
    Orientation,
    PageSize,
    TextAlignment,
)
from src.core.models.template_model import (
    CanvasElement,
    Margins,
    PageSetup,
    Template,
)

_BASE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent.parent))
DEFAULT_TEMPLATES_DIR = _BASE_ROOT / "assets" / "templates"


@dataclass
class TemplateImportReport:
    """Result report produced when importing an external DOCX, PDF, or `.qpt` template."""

    template: Template
    source_path: Path
    source_format: str
    editable_elements_count: int
    uses_visual_backdrop: bool
    warnings: List[str] = field(default_factory=list)
    summary_message: str = ""


class TemplateStore:
    """Manages built-in and user-created visual templates without affecting saved question papers."""

    def __init__(self, storage_dir: Optional[Path | str] = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_TEMPLATES_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_builtin_templates()

    @staticmethod
    def build_default_templates() -> List[Template]:
        """Construct the 3 built-in visual templates (Standard School A4, University 2-Col, Minimal Exam)."""
        # 1. Standard School A4 Template
        school_template = Template(
            template_id="builtin-standard-school-a4",
            name="Standard School A4",
            is_builtin=True,
            page_setup=PageSetup(
                size=PageSize.A4,
                orientation=Orientation.PORTRAIT,
                margins_mm=Margins(top=15.0, bottom=15.0, left=15.0, right=15.0),
            ),
            header_height_mm=38.0,
            footer_height_mm=14.0,
            different_first_page=True,
            first_page_header_elements=[
                CanvasElement(
                    element_id="school-title",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=2.0,
                    width_mm=180.0,
                    height_mm=8.0,
                    font_family="Noto Sans",
                    font_size_pt=14.0,
                    bold=True,
                    alignment=TextAlignment.CENTER,
                    content="{{exam_name}}",
                ),
                CanvasElement(
                    element_id="school-subject",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=11.0,
                    width_mm=180.0,
                    height_mm=7.0,
                    font_family="Noto Sans",
                    font_size_pt=12.0,
                    bold=True,
                    alignment=TextAlignment.CENTER,
                    content="Subject: {{subject_name}} ({{class_semester}})",
                ),
                CanvasElement(
                    element_id="school-time-left",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=20.0,
                    width_mm=85.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=10.5,
                    bold=True,
                    alignment=TextAlignment.LEFT,
                    content="Time: {{duration}}",
                ),
                CanvasElement(
                    element_id="school-marks-right",
                    element_type=CanvasElementType.TEXT,
                    x_mm=95.0,
                    y_mm=20.0,
                    width_mm=85.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=10.5,
                    bold=True,
                    alignment=TextAlignment.RIGHT,
                    content="Max. Marks: {{max_marks}}",
                ),
                CanvasElement(
                    element_id="school-divider",
                    element_type=CanvasElementType.LINE,
                    x_mm=0.0,
                    y_mm=28.0,
                    width_mm=180.0,
                    height_mm=1.0,
                    line_thickness_pt=1.5,
                ),
            ],
            running_header_elements=[
                CanvasElement(
                    element_id="school-running-hdr",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=4.0,
                    width_mm=180.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.5,
                    italic=True,
                    alignment=TextAlignment.CENTER,
                    content="{{exam_name}} — {{subject_name}}",
                ),
            ],
            first_page_footer_elements=[
                CanvasElement(
                    element_id="school-footer-page",
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=3.0,
                    width_mm=180.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.5,
                    alignment=TextAlignment.CENTER,
                    content="Page {{page_number}} of {{total_pages}}",
                )
            ],
            running_footer_elements=[
                CanvasElement(
                    element_id="school-running-footer-page",
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=3.0,
                    width_mm=180.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.5,
                    alignment=TextAlignment.CENTER,
                    content="Page {{page_number}} of {{total_pages}}",
                )
            ],
        )

        # 2. University Two-Column Examination Template
        university_template = Template(
            template_id="builtin-university-two-column",
            name="University Two-Column",
            is_builtin=True,
            page_setup=PageSetup(
                size=PageSize.A4,
                orientation=Orientation.PORTRAIT,
                margins_mm=Margins(top=12.0, bottom=12.0, left=12.0, right=12.0),
            ),
            header_height_mm=42.0,
            footer_height_mm=14.0,
            different_first_page=True,
            first_page_header_elements=[
                CanvasElement(
                    element_id="uni-code-set",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=2.0,
                    width_mm=186.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=10.0,
                    bold=True,
                    alignment=TextAlignment.RIGHT,
                    content="Paper Code: {{subject_code}}   |   {{set_identifier}}",
                ),
                CanvasElement(
                    element_id="uni-exam-title",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=9.0,
                    width_mm=186.0,
                    height_mm=8.0,
                    font_family="Noto Sans",
                    font_size_pt=13.5,
                    bold=True,
                    alignment=TextAlignment.CENTER,
                    content="{{exam_name}}",
                ),
                CanvasElement(
                    element_id="uni-course",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=18.0,
                    width_mm=186.0,
                    height_mm=7.0,
                    font_family="Noto Sans",
                    font_size_pt=11.5,
                    bold=True,
                    alignment=TextAlignment.CENTER,
                    content="{{class_semester}} — {{subject_name}}",
                ),
                CanvasElement(
                    element_id="uni-meta-line",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=27.0,
                    width_mm=186.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=10.0,
                    bold=True,
                    alignment=TextAlignment.CENTER,
                    content="Duration: {{duration}}                                        Maximum Marks: {{max_marks}}",
                ),
                CanvasElement(
                    element_id="uni-rule",
                    element_type=CanvasElementType.LINE,
                    x_mm=0.0,
                    y_mm=35.0,
                    width_mm=186.0,
                    height_mm=1.0,
                    line_thickness_pt=1.5,
                ),
            ],
            running_header_elements=[
                CanvasElement(
                    element_id="uni-running-code",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=4.0,
                    width_mm=186.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.0,
                    alignment=TextAlignment.RIGHT,
                    content="{{subject_code}} ({{set_identifier}})",
                )
            ],
            first_page_footer_elements=[
                CanvasElement(
                    element_id="uni-footer-pg",
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=3.0,
                    width_mm=186.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.5,
                    alignment=TextAlignment.CENTER,
                    content="[ Page {{page_number}} of {{total_pages}} ]",
                )
            ],
            running_footer_elements=[
                CanvasElement(
                    element_id="uni-running-footer-pg",
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=3.0,
                    width_mm=186.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.5,
                    alignment=TextAlignment.CENTER,
                    content="[ Page {{page_number}} of {{total_pages}} ]",
                )
            ],
        )

        # 3. Minimal Compact Test Template
        minimal_template = Template(
            template_id="builtin-minimal-exam",
            name="Minimal Exam",
            is_builtin=True,
            page_setup=PageSetup(
                size=PageSize.A4,
                orientation=Orientation.PORTRAIT,
                margins_mm=Margins(top=15.0, bottom=15.0, left=15.0, right=15.0),
            ),
            header_height_mm=24.0,
            footer_height_mm=12.0,
            different_first_page=False,
            running_header_elements=[
                CanvasElement(
                    element_id="min-hdr-left",
                    element_type=CanvasElementType.TEXT,
                    x_mm=0.0,
                    y_mm=3.0,
                    width_mm=110.0,
                    height_mm=7.0,
                    font_family="Noto Sans",
                    font_size_pt=12.0,
                    bold=True,
                    alignment=TextAlignment.LEFT,
                    content="{{exam_name}} — {{subject_name}}",
                ),
                CanvasElement(
                    element_id="min-hdr-right",
                    element_type=CanvasElementType.TEXT,
                    x_mm=110.0,
                    y_mm=3.0,
                    width_mm=70.0,
                    height_mm=7.0,
                    font_family="Noto Sans",
                    font_size_pt=10.5,
                    bold=True,
                    alignment=TextAlignment.RIGHT,
                    content="{{duration}} | {{max_marks}} Marks",
                ),
                CanvasElement(
                    element_id="min-hdr-line",
                    element_type=CanvasElementType.LINE,
                    x_mm=0.0,
                    y_mm=13.0,
                    width_mm=180.0,
                    height_mm=1.0,
                    line_thickness_pt=1.0,
                ),
            ],
            running_footer_elements=[
                CanvasElement(
                    element_id="min-ftr-pg",
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=2.0,
                    width_mm=180.0,
                    height_mm=6.0,
                    font_family="Noto Sans",
                    font_size_pt=9.0,
                    alignment=TextAlignment.RIGHT,
                    content="Page {{page_number}}",
                )
            ],
        )

        return [school_template, university_template, minimal_template]

    def ensure_builtin_templates(self) -> List[Path]:
        """Write built-in default templates to `self.storage_dir` if missing."""
        written: List[Path] = []
        for tmpl in self.build_default_templates():
            target = self.storage_dir / f"{tmpl.template_id}.qpt.json"
            if not target.exists():
                target.write_text(tmpl.model_dump_json(indent=2), encoding="utf-8")
            written.append(target)
        return written

    def list_templates(self) -> List[Template]:
        """Load and return all templates stored in `self.storage_dir`."""
        self.ensure_builtin_templates()
        templates: List[Template] = []
        for path in sorted(self.storage_dir.glob("*.json")):
            try:
                raw = path.read_text(encoding="utf-8")
                templates.append(Template.model_validate_json(raw))
            except Exception:
                continue
        return templates

    def get_template(self, template_id: str) -> Optional[Template]:
        """Retrieve a template by `template_id`."""
        for tmpl in self.list_templates():
            if tmpl.template_id == template_id:
                return tmpl
        return None

    def save_template(
        self,
        template: Template,
        custom_path: Optional[Path | str] = None,
        overwrite: bool = True,
    ) -> Path:
        """Save a template to `custom_path` or `self.storage_dir`."""
        template.updated_at = datetime.now(timezone.utc)
        if custom_path is not None:
            dest = Path(custom_path)
            if not dest.name.endswith(".json"):
                dest = dest.with_suffix(".qpt.json")
        else:
            safe_id = "".join(c for c in template.template_id if c.isalnum() or c in ("-", "_"))
            dest = self.storage_dir / f"{safe_id}.qpt.json"

        if dest.exists() and not overwrite:
            raise FileExistsError(f"Template file '{dest}' already exists.")

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(template.model_dump_json(indent=2), encoding="utf-8")
        return dest

    def rename_template(self, template_id: str, new_name: str) -> Template:
        """Rename a template in the store."""
        tmpl = self.get_template(template_id)
        if tmpl is None:
            raise KeyError(f"Template '{template_id}' not found.")
        tmpl.name = new_name.strip()
        self.save_template(tmpl, overwrite=True)
        return tmpl

    def duplicate_template(self, template_id: str, new_name: Optional[str] = None) -> Template:
        """Duplicate an existing template into a new user-editable template."""
        tmpl = self.get_template(template_id)
        if tmpl is None:
            raise KeyError(f"Template '{template_id}' not found.")
        cloned = tmpl.duplicate(new_name=new_name)
        self.save_template(cloned, overwrite=True)
        return cloned

    def delete_template(self, template_id: str) -> bool:
        """Delete a template file from the template library without affecting saved `.qpf` papers."""
        deleted = False
        for path in self.storage_dir.glob("*.json"):
            try:
                tmpl = Template.model_validate_json(path.read_text(encoding="utf-8"))
                if tmpl.template_id == template_id:
                    path.unlink()
                    deleted = True
            except Exception:
                continue
        return deleted

    def import_external_template(
        self,
        source_file: Path | str,
        template_name: Optional[str] = None,
    ) -> TemplateImportReport:
        """Import a template from `.qpt.json`, `.docx`, or `.pdf` without modifying `source_file`.

        Clearly reports which elements were converted into editable `CanvasElement` items
        versus preserved as a static visual backdrop reference.
        """
        src = Path(source_file)
        if not src.exists():
            raise FileNotFoundError(f"Source template file not found: '{src}'")

        ext = src.suffix.lower()
        name = template_name or src.stem

        # Case 1: Native JSON / .qpt template
        if ext in (".json", ".qpt"):
            tmpl = Template.model_validate_json(src.read_text(encoding="utf-8"))
            tmpl = tmpl.duplicate(new_name=name)
            tmpl.source_format = "QPT"
            self.save_template(tmpl, overwrite=True)
            total_els = (
                len(tmpl.first_page_header_elements)
                + len(tmpl.running_header_elements)
                + len(tmpl.first_page_footer_elements)
                + len(tmpl.running_footer_elements)
            )
            return TemplateImportReport(
                template=tmpl,
                source_path=src,
                source_format="QPT",
                editable_elements_count=total_els,
                uses_visual_backdrop=False,
                summary_message=f"Imported {total_els} fully editable canvas elements from native template.",
            )

        # Case 2: Microsoft Word (.docx)
        if ext == ".docx":
            doc = docx.Document(str(src))
            sec = doc.sections[0]

            # Extract page dimensions & margins in millimeters (1 inch = 25.4 mm)
            w_mm = round(sec.page_width.inches * 25.4, 1) if sec.page_width else 210.0
            h_mm = round(sec.page_height.inches * 25.4, 1) if sec.page_height else 297.0
            top_m = round(sec.top_margin.inches * 25.4, 1) if sec.top_margin else 15.0
            bot_m = round(sec.bottom_margin.inches * 25.4, 1) if sec.bottom_margin else 15.0
            left_m = round(sec.left_margin.inches * 25.4, 1) if sec.left_margin else 15.0
            right_m = round(sec.right_margin.inches * 25.4, 1) if sec.right_margin else 15.0

            orientation = Orientation.LANDSCAPE if w_mm > h_mm else Orientation.PORTRAIT
            size_enum = PageSize.A4
            if abs(min(w_mm, h_mm) - 215.9) < 3.0:
                size_enum = PageSize.LETTER
            elif abs(min(w_mm, h_mm) - 297.0) < 3.0 and abs(max(w_mm, h_mm) - 420.0) < 3.0:
                size_enum = PageSize.A3

            printable_w = max(60.0, w_mm - left_m - right_m)
            header_els: List[CanvasElement] = []
            footer_els: List[CanvasElement] = []

            # Extract header paragraphs or top body lines if header is empty
            hdr_lines = [p.text.strip() for p in sec.header.paragraphs if p.text.strip()]
            if not hdr_lines:
                hdr_lines = [p.text.strip() for p in doc.paragraphs[:4] if p.text.strip()]

            y_cursor = 2.0
            for idx, line in enumerate(hdr_lines[:4]):
                header_els.append(
                    CanvasElement(
                        element_type=CanvasElementType.TEXT,
                        x_mm=0.0,
                        y_mm=y_cursor,
                        width_mm=printable_w,
                        height_mm=7.0,
                        font_size_pt=13.0 if idx == 0 else 10.5,
                        bold=(idx <= 1),
                        alignment=TextAlignment.CENTER,
                        content=line,
                    )
                )
                y_cursor += 8.0

            ftr_lines = [p.text.strip() for p in sec.footer.paragraphs if p.text.strip()]
            if ftr_lines:
                footer_els.append(
                    CanvasElement(
                        element_type=CanvasElementType.TEXT,
                        x_mm=0.0,
                        y_mm=2.0,
                        width_mm=printable_w,
                        height_mm=6.0,
                        font_size_pt=9.5,
                        alignment=TextAlignment.CENTER,
                        content=ftr_lines[0],
                    )
                )
            else:
                footer_els.append(
                    CanvasElement(
                        element_type=CanvasElementType.PAGE_NUMBER,
                        x_mm=0.0,
                        y_mm=2.0,
                        width_mm=printable_w,
                        height_mm=6.0,
                        font_size_pt=9.5,
                        alignment=TextAlignment.CENTER,
                        content="Page {{page_number}} of {{total_pages}}",
                    )
                )

            tmpl = Template(
                name=name,
                is_builtin=False,
                page_setup=PageSetup(
                    size=size_enum,
                    orientation=orientation,
                    margins_mm=Margins(
                        top=min(40.0, max(5.0, top_m)),
                        bottom=min(40.0, max(5.0, bot_m)),
                        left=min(40.0, max(5.0, left_m)),
                        right=min(40.0, max(5.0, right_m)),
                    ),
                ),
                header_height_mm=max(30.0, y_cursor + 4.0),
                footer_height_mm=14.0,
                different_first_page=bool(sec.different_first_page_header_footer),
                first_page_header_elements=list(header_els),
                running_header_elements=list(header_els),
                first_page_footer_elements=list(footer_els),
                running_footer_elements=list(footer_els),
                source_format="DOCX",
            )
            self.save_template(tmpl, overwrite=True)
            total_editable = len(header_els) + len(footer_els)
            return TemplateImportReport(
                template=tmpl,
                source_path=src,
                source_format="DOCX",
                editable_elements_count=total_editable,
                uses_visual_backdrop=False,
                summary_message=(
                    f"Extracted page setup and {total_editable} editable header/footer elements from DOCX."
                ),
            )

        # Case 3: PDF Template Import (extracts page geometry + header text + preserves visual backdrop reference)
        if ext == ".pdf":
            reader = PdfReader(str(src))
            w_mm, h_mm = 210.0, 297.0
            extracted_lines: List[str] = []
            if reader.pages:
                first_page = reader.pages[0]
                box = first_page.mediabox
                # 1 pt = 1/72 inch = 25.4 / 72 mm
                w_mm = round(float(box.width) * 25.4 / 72.0, 1)
                h_mm = round(float(box.height) * 25.4 / 72.0, 1)
                try:
                    raw_text = first_page.extract_text() or ""
                    extracted_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()][:3]
                except Exception:
                    extracted_lines = []

            orientation = Orientation.LANDSCAPE if w_mm > h_mm else Orientation.PORTRAIT
            printable_w = max(60.0, min(w_mm, h_mm) - 30.0)
            header_els = []
            y_pos = 3.0
            for idx, ln in enumerate(extracted_lines):
                header_els.append(
                    CanvasElement(
                        element_type=CanvasElementType.TEXT,
                        x_mm=0.0,
                        y_mm=y_pos,
                        width_mm=printable_w,
                        height_mm=7.0,
                        font_size_pt=12.0 if idx == 0 else 10.0,
                        bold=(idx == 0),
                        alignment=TextAlignment.CENTER,
                        content=ln,
                    )
                )
                y_pos += 8.0

            footer_els = [
                CanvasElement(
                    element_type=CanvasElementType.PAGE_NUMBER,
                    x_mm=0.0,
                    y_mm=2.0,
                    width_mm=printable_w,
                    height_mm=6.0,
                    font_size_pt=9.5,
                    alignment=TextAlignment.CENTER,
                    content="Page {{page_number}} of {{total_pages}}",
                )
            ]

            tmpl = Template(
                name=name,
                is_builtin=False,
                page_setup=PageSetup(
                    size=PageSize.A4,
                    orientation=orientation,
                ),
                header_height_mm=36.0,
                footer_height_mm=14.0,
                running_header_elements=header_els,
                running_footer_elements=footer_els,
                imported_backdrop_asset=str(src.resolve()),
                source_format="PDF",
            )
            self.save_template(tmpl, overwrite=True)
            return TemplateImportReport(
                template=tmpl,
                source_path=src,
                source_format="PDF",
                editable_elements_count=len(header_els) + len(footer_els),
                uses_visual_backdrop=True,
                warnings=[
                    "Vector graphics in the source PDF are preserved as a visual backdrop reference; extracted text lines are editable."
                ],
                summary_message=(
                    f"Imported PDF template with {len(header_els)} editable text elements and visual backdrop reference."
                ),
            )

        raise ValueError(f"Unsupported template file format: '{ext}'")
