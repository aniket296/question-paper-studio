"""Native Editable Microsoft Word (`.docx`) Compiler with OMML Math Equations & Word Fields.

Generates fully editable `.docx` question papers, Answer Keys, and Marking Schemes using `python-docx` + `lxml`:
- Exact millimeter page dimensions, orientation, and margins on Word `Section` properties.
- Word Headers & Footers supporting `different_first_page_header_footer = True` and native Word
  `PAGE` and `NUMPAGES` XML fields (`<w:fldSimple w:instr="PAGE"/>`).
- Questions rendered with `keep_with_next` / `keep_together` rules, right-aligned tab stops for marks,
  borderless 2x2 or 4-col tables for MCQ options, bordered 2-column tables for Match the Pair,
  embedded images with exact millimeter widths, and native editable `<m:oMath>` equations.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import docx
from docx.document import Document as DocxDocument
from docx.enum.section import WD_ORIENTATION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from docx.text.paragraph import Paragraph

from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import NumberingFSM
from src.core.models.enums import (
    BilingualLayout,
    CanvasElementType,
    ChoiceRuleType,
    FillBlankMode,
    MCQOptionLayout,
    Orientation,
    QuestionType,
    TextAlignment,
)
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    AssertionReasonData,
    CaseBasedData,
    DiagramAttachment,
    DiagramLabellingData,
    FillBlankData,
    MCQData,
    MatchPairData,
    NumericalDynamicData,
    OrderingSequencingData,
    QuestionNode,
    SourceBasedData,
    TrueFalseData,
)
from src.core.models.section_model import Section, SharedPassage
from src.core.models.template_model import CanvasElement
from src.rendering.math_converter import MathConverter
from src.rendering.supplementary_builder import SupplementaryBuilder


def _strip_tags_preserve_text(raw_html: str) -> str:
    """Convert basic HTML line breaks to newlines and strip HTML tags while unescaping entities."""
    txt = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    txt = re.sub(r"</p\s*>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", "", txt)
    return html.unescape(txt).strip()


def _hex_to_rgb(color_hex: str) -> RGBColor:
    cleaned = color_hex.lstrip("#")
    if len(cleaned) == 6:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return RGBColor(r, g, b)
    return RGBColor(0, 0, 0)


def _align_to_wd(alignment: TextAlignment) -> WD_ALIGN_PARAGRAPH:
    mapping = {
        TextAlignment.LEFT: WD_ALIGN_PARAGRAPH.LEFT,
        TextAlignment.CENTER: WD_ALIGN_PARAGRAPH.CENTER,
        TextAlignment.RIGHT: WD_ALIGN_PARAGRAPH.RIGHT,
        TextAlignment.JUSTIFY: WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    return mapping.get(alignment, WD_ALIGN_PARAGRAPH.LEFT)


def _append_word_field(paragraph: Paragraph, field_name: str) -> None:
    """Append a native Word simple field (`PAGE` or `NUMPAGES`) to `paragraph`."""
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), f" {field_name} \\* MERGEFORMAT ")
    run_el = OxmlElement("w:r")
    t_el = OxmlElement("w:t")
    t_el.text = "1"
    run_el.append(t_el)
    fld.append(run_el)
    paragraph._p.append(fld)


def _set_table_borderless(table: docx.table.Table) -> None:
    """Remove all cell/table borders on a python-docx Table via OpenXML `<w:tblBorders>`."""
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b_el = OxmlElement(f"w:{border_name}")
        b_el.set(qn("w:val"), "none")
        b_el.set(qn("w:sz"), "0")
        b_el.set(qn("w:space"), "0")
        b_el.set(qn("w:color"), "auto")
        borders.append(b_el)
    tbl_pr.append(borders)


def _set_row_cant_split(row: docx.table._Row) -> None:
    """Prevent a Word table row from splitting across a page break (`<w:cantSplit/>`)."""
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


class DOCXExporter:
    """Compiles a `ProjectState` AST, Answer Key, or Marking Scheme into a native editable `.docx`."""

    @staticmethod
    def _append_rich_text_and_omml(
        paragraph: Paragraph,
        raw_html: str,
        font_name: str = "Noto Sans",
        font_size_pt: float = 11.0,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color_hex: str = "#000000",
    ) -> None:
        """Append text and native `<m:oMath>` equations to `paragraph`."""
        plain = _strip_tags_preserve_text(raw_html)
        segments = MathConverter.split_text_and_math(plain)
        rgb = _hex_to_rgb(color_hex)

        for seg in segments:
            if seg.is_math:
                omml_el = MathConverter.latex_to_omml_element(
                    seg.content,
                    display_block=False,
                )
                paragraph._p.append(omml_el)
            else:
                run = paragraph.add_run(seg.content)
                run.font.name = font_name
                run.font.size = Pt(font_size_pt)
                run.bold = bold
                run.italic = italic
                run.underline = underline
                run.font.color.rgb = rgb

    @staticmethod
    def _populate_header_or_footer(
        hf_container: docx.section._Header | docx.section._Footer,
        elements: List[CanvasElement],
        placeholder_ctx: Dict[str, str],
        base_asset_dir: Optional[Path] = None,
    ) -> None:
        """Populate a Word Header or Footer with template `CanvasElement` items and native PAGE/NUMPAGES fields."""
        # Clear default empty paragraph text
        for p in hf_container.paragraphs:
            p.text = ""

        sorted_els = sorted(elements, key=lambda e: (e.y_mm, e.x_mm))
        for idx, el in enumerate(sorted_els):
            para = hf_container.paragraphs[0] if (idx == 0 and hf_container.paragraphs) else hf_container.add_paragraph()
            para.alignment = _align_to_wd(el.alignment)
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(2)

            if el.element_type == CanvasElementType.LINE:
                p_bdr = OxmlElement("w:pBdr")
                bottom = OxmlElement("w:bottom")
                bottom.set(qn("w:val"), "single")
                bottom.set(qn("w:sz"), str(max(4, int(el.line_thickness_pt * 8))))
                bottom.set(qn("w:space"), "1")
                bottom.set(qn("w:color"), el.color_hex.lstrip("#"))
                p_bdr.append(bottom)
                para._p.get_or_add_pPr().append(p_bdr)
                continue

            if el.element_type == CanvasElementType.IMAGE and el.content:
                img_path = Path(el.content)
                if not img_path.is_absolute() and base_asset_dir is not None:
                    img_path = (base_asset_dir / el.content).resolve()
                if img_path.exists() and img_path.is_file():
                    run = para.add_run()
                    run.add_picture(str(img_path), width=Mm(el.width_mm))
                continue

            if el.element_type == CanvasElementType.PAGE_NUMBER or "{{page_number}}" in el.content:
                # Substitute non-page placeholders first, then inject native Word PAGE & NUMPAGES fields
                raw = el.content
                for k, v in placeholder_ctx.items():
                    if k not in ("{{page_number}}", "{{total_pages}}"):
                        raw = raw.replace(k, v)

                tokens = re.split(r"(\{\{page_number\}\}|\{\{total_pages\}\})", raw)
                for tok in tokens:
                    if tok == "{{page_number}}":
                        _append_word_field(para, "PAGE")
                    elif tok == "{{total_pages}}":
                        _append_word_field(para, "NUMPAGES")
                    elif tok:
                        r = para.add_run(tok)
                        r.font.name = el.font_family
                        r.font.size = Pt(el.font_size_pt)
                        r.bold = el.bold
                        r.italic = el.italic
                        r.underline = el.underline
                        r.font.color.rgb = _hex_to_rgb(el.color_hex)
            else:
                rendered = el.render_placeholders(placeholder_ctx)
                r = para.add_run(rendered)
                r.font.name = el.font_family
                r.font.size = Pt(el.font_size_pt)
                r.bold = el.bold
                r.italic = el.italic
                r.underline = el.underline
                r.font.color.rgb = _hex_to_rgb(el.color_hex)

    @staticmethod
    def _configure_word_section_and_headers(
        doc: DocxDocument,
        project: ProjectState,
        base_asset_dir: Optional[Path] = None,
    ) -> float:
        """Configure page dimensions, orientation, margins, and headers/footers; return printable width in mm."""
        tmpl = project.template_snapshot
        setup = tmpl.page_setup
        w_mm, h_mm = setup.effective_dimensions_mm
        m = setup.margins_mm

        word_sec = doc.sections[0]
        word_sec.orientation = (
            WD_ORIENTATION.LANDSCAPE
            if setup.orientation == Orientation.LANDSCAPE
            else WD_ORIENTATION.PORTRAIT
        )
        word_sec.page_width = Mm(w_mm)
        word_sec.page_height = Mm(h_mm)
        word_sec.top_margin = Mm(m.top)
        word_sec.bottom_margin = Mm(m.bottom)
        word_sec.left_margin = Mm(m.left)
        word_sec.right_margin = Mm(m.right)

        marks_report = MarksEngine.audit_project_marks(project)
        placeholder_ctx = project.exam_metadata.to_placeholder_context()
        if not placeholder_ctx["{{max_marks}}"] and marks_report.total_effective_marks > 0:
            eff = marks_report.total_effective_marks
            placeholder_ctx["{{max_marks}}"] = str(int(eff)) if float(eff).is_integer() else f"{eff:g}"

        word_sec.different_first_page_header_footer = tmpl.different_first_page
        if tmpl.different_first_page:
            DOCXExporter._populate_header_or_footer(
                word_sec.first_page_header,
                tmpl.get_header_elements(is_first_page=True),
                placeholder_ctx,
                base_asset_dir=base_asset_dir,
            )
            DOCXExporter._populate_header_or_footer(
                word_sec.first_page_footer,
                tmpl.get_footer_elements(is_first_page=True),
                placeholder_ctx,
                base_asset_dir=base_asset_dir,
            )

        DOCXExporter._populate_header_or_footer(
            word_sec.header,
            tmpl.get_header_elements(is_first_page=False),
            placeholder_ctx,
            base_asset_dir=base_asset_dir,
        )
        DOCXExporter._populate_header_or_footer(
            word_sec.footer,
            tmpl.get_footer_elements(is_first_page=False),
            placeholder_ctx,
            base_asset_dir=base_asset_dir,
        )

        return setup.printable_width_mm

    @staticmethod
    def export_project_to_docx(
        project: ProjectState,
        output_path: Path | str,
        teacher_preview_mode: bool = False,
        overwrite: bool = True,
        base_asset_dir: Optional[Path] = None,
        dynamic_seed: int = 101,
    ) -> Path:
        """Compile `project` into a fully editable `.docx` file at `output_path`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".docx":
            dest = dest.with_suffix(".docx")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"DOCX file '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)

        NumberingFSM.resolve_project(project)
        doc = docx.Document()
        printable_w_mm = DOCXExporter._configure_word_section_and_headers(
            doc,
            project,
            base_asset_dir=base_asset_dir,
        )

        # Configure base Normal style font
        normal_style = doc.styles["Normal"]
        normal_style.font.name = project.layout_settings.base_font_family or "Noto Sans"
        normal_style.font.size = Pt(project.layout_settings.base_font_size_pt)

        # 1. Candidate Info Table if enabled
        if project.exam_metadata.candidate_fields:
            fields = project.exam_metadata.candidate_fields
            row_count = (len(fields) + 1) // 2
            cand_tbl = doc.add_table(rows=row_count, cols=2)
            cand_tbl.style = "Table Grid"
            cand_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            for idx, cf in enumerate(fields):
                r_idx, c_idx = divmod(idx, 2)
                cell = cand_tbl.cell(r_idx, c_idx)
                cell.text = f"{cf.value}: ________________________"
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True
                        run.font.size = Pt(9.5)

        # 2. General Instructions if present
        if project.exam_metadata.general_instructions.strip():
            instr_hdr = doc.add_paragraph()
            instr_hdr.paragraph_format.keep_with_next = True
            r_hdr = instr_hdr.add_run("General Instructions:")
            r_hdr.bold = True
            instr_body = doc.add_paragraph()
            instr_body.paragraph_format.keep_together = True
            DOCXExporter._append_rich_text_and_omml(
                instr_body,
                project.exam_metadata.general_instructions,
                font_size_pt=project.layout_settings.base_font_size_pt - 0.5,
            )

        # 3. Render Sections and Questions
        for sec in project.sections:
            DOCXExporter._render_section_to_docx(
                doc=doc,
                project=project,
                section=sec,
                printable_w_mm=printable_w_mm,
                teacher_preview_mode=teacher_preview_mode,
                base_asset_dir=base_asset_dir,
                dynamic_seed=dynamic_seed,
            )

        doc.save(str(dest))
        return dest

    @staticmethod
    def _render_section_to_docx(
        doc: DocxDocument,
        project: ProjectState,
        section: Section,
        printable_w_mm: float,
        teacher_preview_mode: bool,
        base_asset_dir: Optional[Path],
        dynamic_seed: int,
    ) -> None:
        base_pt = project.layout_settings.base_font_size_pt

        if not section.is_default_unsectioned:
            sec_p = doc.add_paragraph()
            sec_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            sec_p.paragraph_format.keep_with_next = True
            sec_p.paragraph_format.space_before = Pt(8)
            sec_p.paragraph_format.space_after = Pt(3)
            r_title = sec_p.add_run(section.title.upper())
            r_title.bold = True
            r_title.font.size = Pt(base_pt + 1.0)

            if section.instructions_html.strip():
                inst_p = doc.add_paragraph()
                inst_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                inst_p.paragraph_format.keep_with_next = True
                DOCXExporter._append_rich_text_and_omml(
                    inst_p,
                    section.instructions_html,
                    font_size_pt=base_pt - 0.5,
                    italic=True,
                )

        # Shared passages & choice groups lookup
        passage_by_first_qid: Dict[str, SharedPassage] = {}
        passage_by_id: Dict[str, SharedPassage] = {}
        for sp in section.shared_passages:
            passage_by_id[sp.passage_id] = sp
            if sp.linked_question_ids:
                passage_by_first_qid[sp.linked_question_ids[0]] = sp
        rendered_passages: Set[str] = set()

        or_after_qid: Dict[str, str] = {}
        any_k_before_qid: Dict[str, str] = {}
        for cg in section.choice_groups:
            if not cg.question_ids:
                continue
            if cg.rule_type == ChoiceRuleType.OR_PAIR and len(cg.question_ids) >= 2:
                for qid in cg.question_ids[:-1]:
                    or_after_qid[qid] = cg.label_text or "OR"
            elif cg.rule_type == ChoiceRuleType.ANY_K_OF_N:
                any_k_before_qid[cg.question_ids[0]] = (
                    f"Answer any {cg.attempt_count_k} of the following {len(cg.question_ids)} questions:"
                )

        for q in section.questions:
            sp_cand = passage_by_first_qid.get(q.question_id) or (
                passage_by_id.get(q.shared_passage_id) if q.shared_passage_id else None
            )
            if sp_cand is not None and sp_cand.passage_id not in rendered_passages:
                rendered_passages.add(sp_cand.passage_id)
                sp_p = doc.add_paragraph()
                sp_p.paragraph_format.keep_with_next = True
                sp_p.paragraph_format.keep_together = True
                if sp_cand.title:
                    r_spt = sp_p.add_run(f"{sp_cand.title}: ")
                    r_spt.bold = True
                DOCXExporter._append_rich_text_and_omml(
                    sp_p,
                    sp_cand.content_html,
                    font_size_pt=base_pt,
                )

            if q.question_id in any_k_before_qid:
                cg_p = doc.add_paragraph()
                cg_p.paragraph_format.keep_with_next = True
                r_cg = cg_p.add_run(any_k_before_qid[q.question_id])
                r_cg.bold = True
                r_cg.italic = True

            DOCXExporter._render_question_node_to_docx(
                doc=doc,
                project=project,
                node=q,
                printable_w_mm=printable_w_mm,
                depth=0,
                teacher_preview_mode=teacher_preview_mode,
                base_asset_dir=base_asset_dir,
                dynamic_seed=dynamic_seed,
            )

            if q.question_id in or_after_qid:
                or_p = doc.add_paragraph()
                or_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                or_p.paragraph_format.keep_with_next = True
                r_or = or_p.add_run(f"— {or_after_qid[q.question_id]} —")
                r_or.bold = True

    @staticmethod
    def _render_question_node_to_docx(
        doc: DocxDocument,
        project: ProjectState,
        node: QuestionNode,
        printable_w_mm: float,
        depth: int,
        teacher_preview_mode: bool,
        base_asset_dir: Optional[Path],
        dynamic_seed: int,
    ) -> None:
        if node.page_break_before:
            doc.add_page_break()

        layout = project.layout_settings
        base_pt = layout.base_font_size_pt
        q_summary = MarksEngine.calculate_question_effective_marks(node)

        # Resolve prompt text (including Dynamic Numerical variable instantiation)
        raw_prompt = node.prompt_html
        if node.question_type == QuestionType.NUMERICAL_DYNAMIC and isinstance(
            node.type_data, NumericalDynamicData
        ):
            if node.type_data.variables:
                inst = DynamicNumericEngine.instantiate_question(
                    raw_prompt,
                    node.type_data,
                    seed=dynamic_seed,
                )
                raw_prompt = inst.instantiated_text

        q_para = doc.add_paragraph()
        q_para.paragraph_format.keep_together = True
        q_para.paragraph_format.left_indent = Mm(depth * 7.0)
        q_para.paragraph_format.space_before = Pt(3)
        q_para.paragraph_format.space_after = Pt(2)

        # Keep parent prompt attached to its options, tables, or child subquestions
        has_following_block = bool(
            node.children
            or node.diagrams
            or node.question_type in (QuestionType.MCQ, QuestionType.MATCH_THE_PAIR, QuestionType.ASSERTION_REASON)
        )
        if has_following_block:
            q_para.paragraph_format.keep_with_next = True

        # Configure right-aligned tab stop at printable margin for marks
        q_para.paragraph_format.tab_stops.add_tab_stop(
            Mm(printable_w_mm),
            WD_TAB_ALIGNMENT.RIGHT,
        )

        # Question number prefix
        r_num = q_para.add_run(f"{node.resolved_number} ")
        r_num.bold = True
        r_num.font.size = Pt(base_pt)

        # Question prompt with native OMML math
        DOCXExporter._append_rich_text_and_omml(
            q_para,
            raw_prompt,
            font_name=layout.base_font_family,
            font_size_pt=base_pt,
        )

        # Bilingual secondary prompt
        if layout.bilingual_mode and node.prompt_secondary_html:
            if layout.bilingual_layout == BilingualLayout.SIDE_BY_SIDE:
                q_para.add_run("   /   ")
                DOCXExporter._append_rich_text_and_omml(
                    q_para,
                    node.prompt_secondary_html,
                    font_name="Noto Sans Devanagari",
                    font_size_pt=base_pt,
                )
            else:
                q_para.add_run("\n")
                DOCXExporter._append_rich_text_and_omml(
                    q_para,
                    node.prompt_secondary_html,
                    font_name="Noto Sans Devanagari",
                    font_size_pt=base_pt,
                )

        # Right-aligned marks via tab stop
        if layout.show_marks and q_summary.effective_marks > 0:
            eff = q_summary.effective_marks
            m_str = str(int(eff)) if float(eff).is_integer() else f"{eff:g}"
            r_marks = q_para.add_run(f"\t[{m_str}]")
            r_marks.bold = True
            r_marks.font.size = Pt(base_pt)

        # Attached Diagrams
        for diag in node.diagrams:
            DOCXExporter._render_diagram_to_docx(doc, diag, base_asset_dir=base_asset_dir)

        # Question Type Payload (MCQ borderless grid, Match Pair bordered table, Blank word bank, etc.)
        DOCXExporter._render_type_payload_to_docx(
            doc=doc,
            node=node,
            base_pt=base_pt,
            depth=depth,
            teacher_preview_mode=teacher_preview_mode,
        )

        # Answer space lines if configured
        if node.answer_space_lines > 0:
            for _ in range(node.answer_space_lines):
                line_p = doc.add_paragraph("_" * 78)
                line_p.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
                line_p.paragraph_format.space_before = Pt(2)
                line_p.paragraph_format.space_after = Pt(2)

        # Recurse for child subquestions
        for child in node.children:
            DOCXExporter._render_question_node_to_docx(
                doc=doc,
                project=project,
                node=child,
                printable_w_mm=printable_w_mm,
                depth=depth + 1,
                teacher_preview_mode=teacher_preview_mode,
                base_asset_dir=base_asset_dir,
                dynamic_seed=dynamic_seed,
            )

    @staticmethod
    def _render_diagram_to_docx(
        doc: DocxDocument,
        diag: DiagramAttachment,
        base_asset_dir: Optional[Path],
    ) -> None:
        img_path = Path(diag.asset_path)
        if not img_path.is_absolute() and base_asset_dir is not None:
            img_path = (base_asset_dir / diag.asset_path).resolve()

        if img_path.exists() and img_path.is_file():
            img_p = doc.add_paragraph()
            img_p.alignment = _align_to_wd(diag.alignment)
            img_p.paragraph_format.keep_together = True
            run = img_p.add_run()
            run.add_picture(str(img_path), width=Mm(diag.width_mm))
            if diag.caption.strip():
                cap_p = doc.add_paragraph(diag.caption.strip())
                cap_p.alignment = _align_to_wd(diag.alignment)
                for r in cap_p.runs:
                    r.italic = True
                    r.font.size = Pt(9.5)

    @staticmethod
    def _render_type_payload_to_docx(
        doc: DocxDocument,
        node: QuestionNode,
        base_pt: float,
        depth: int,
        teacher_preview_mode: bool,
    ) -> None:
        tdata = node.type_data

        # 1. MCQ Options (Borderless 2x2 or 4-col or stacked table)
        if node.question_type == QuestionType.MCQ and isinstance(tdata, MCQData) and tdata.options:
            opts = tdata.options
            if tdata.option_layout == MCQOptionLayout.INLINE:
                cols = min(4, max(1, len(opts)))
            elif tdata.option_layout == MCQOptionLayout.STACKED:
                cols = 1
            else:
                cols = 2

            rows_needed = (len(opts) + cols - 1) // cols
            opt_tbl = doc.add_table(rows=rows_needed, cols=cols)
            _set_table_borderless(opt_tbl)
            for row in opt_tbl.rows:
                _set_row_cant_split(row)

            correct_labels: List[str] = []
            for idx, opt in enumerate(opts):
                if opt.is_correct:
                    correct_labels.append(opt.label)
                r_idx, c_idx = divmod(idx, cols)
                cell = opt_tbl.cell(r_idx, c_idx)
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.space_after = Pt(1)
                r_lbl = p.add_run(f"({opt.label}) ")
                r_lbl.bold = True
                r_lbl.font.size = Pt(base_pt)
                DOCXExporter._append_rich_text_and_omml(p, opt.text_html, font_size_pt=base_pt)

            if teacher_preview_mode and correct_labels:
                kp = doc.add_paragraph()
                r_k = kp.add_run(f"Answer Key: Option {', '.join(correct_labels)}")
                r_k.bold = True
                r_k.font.color.rgb = RGBColor(5, 150, 105)

        # 2. Fill in the Blank Word Bank
        elif node.question_type == QuestionType.FILL_IN_THE_BLANK and isinstance(tdata, FillBlankData):
            if tdata.mode == FillBlankMode.WITH_OPTIONS and tdata.word_bank_options:
                wb_p = doc.add_paragraph()
                wb_p.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
                r_wb = wb_p.add_run(f"Options: ( {' / '.join(tdata.word_bank_options)} )")
                r_wb.italic = True

        # 3. Match the Pair (Bordered 2-Column Table)
        elif node.question_type == QuestionType.MATCH_THE_PAIR and isinstance(tdata, MatchPairData):
            mp_tbl = doc.add_table(rows=len(tdata.rows) + 1, cols=2)
            mp_tbl.style = "Table Grid"
            hdr_cells = mp_tbl.rows[0].cells
            hdr_cells[0].text = tdata.col_a_header
            hdr_cells[1].text = tdata.col_b_header
            for hc in hdr_cells:
                for p in hc.paragraphs:
                    for r in p.runs:
                        r.bold = True

            col_b_by_disp: Dict[int, str] = {}
            for idx, r in enumerate(tdata.rows):
                disp_idx = r.shuffled_col_b_index if r.shuffled_col_b_index is not None else idx
                col_b_by_disp[disp_idx] = r.col_b_html

            for idx, r in enumerate(tdata.rows):
                row_obj = mp_tbl.rows[idx + 1]
                _set_row_cant_split(row_obj)
                c_a, c_b = row_obj.cells[0], row_obj.cells[1]
                roman_lbl = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")[idx % 10]
                alpha_lbl = chr(ord("A") + (idx % 26))

                p_a = c_a.paragraphs[0]
                p_a.add_run(f"({roman_lbl}) ").bold = True
                DOCXExporter._append_rich_text_and_omml(p_a, r.col_a_html, font_size_pt=base_pt)

                p_b = c_b.paragraphs[0]
                p_b.add_run(f"({alpha_lbl}) ").bold = True
                DOCXExporter._append_rich_text_and_omml(
                    p_b,
                    col_b_by_disp.get(idx, r.col_b_html),
                    font_size_pt=base_pt,
                )

        # 4. True / False
        elif node.question_type == QuestionType.TRUE_FALSE and isinstance(tdata, TrueFalseData):
            tf_p = doc.add_paragraph("[ True / False ]")
            tf_p.paragraph_format.left_indent = Mm((depth + 1) * 7.0)

        # 5. Assertion & Reason
        elif node.question_type == QuestionType.ASSERTION_REASON and isinstance(tdata, AssertionReasonData):
            ar_p = doc.add_paragraph()
            ar_p.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
            ar_p.add_run("Assertion (A): ").bold = True
            DOCXExporter._append_rich_text_and_omml(ar_p, tdata.assertion_html, font_size_pt=base_pt)
            ar_p.add_run("\nReason (R): ").bold = True
            DOCXExporter._append_rich_text_and_omml(ar_p, tdata.reason_html, font_size_pt=base_pt)
            for idx, opt_str in enumerate(tdata.options):
                lbl = chr(ord("A") + idx)
                op = doc.add_paragraph(f"({lbl}) {opt_str}")
                op.paragraph_format.left_indent = Mm((depth + 1) * 7.0)

        # 6. Case-Based / Source-Based / Ordering / Diagram Labelling
        elif node.question_type == QuestionType.CASE_BASED and isinstance(tdata, CaseBasedData):
            if tdata.case_passage_html.strip():
                cp = doc.add_paragraph()
                cp.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
                if tdata.case_title:
                    cp.add_run(f"{tdata.case_title}: ").bold = True
                DOCXExporter._append_rich_text_and_omml(cp, tdata.case_passage_html, font_size_pt=base_pt)

        elif node.question_type == QuestionType.SOURCE_BASED and isinstance(tdata, SourceBasedData):
            if tdata.source_excerpt_html.strip():
                sp = doc.add_paragraph()
                sp.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
                DOCXExporter._append_rich_text_and_omml(
                    sp,
                    tdata.source_excerpt_html,
                    font_size_pt=base_pt,
                    italic=True,
                )

        elif node.question_type == QuestionType.ORDERING_SEQUENCING and isinstance(
            tdata, OrderingSequencingData
        ):
            for idx, item in enumerate(tdata.items, start=1):
                ip = doc.add_paragraph()
                ip.paragraph_format.left_indent = Mm((depth + 1) * 7.0)
                ip.add_run(f"({idx}) ").bold = True
                DOCXExporter._append_rich_text_and_omml(ip, item.text_html, font_size_pt=base_pt)

        elif node.question_type == QuestionType.DIAGRAM_LABELLING and isinstance(
            tdata, DiagramLabellingData
        ):
            for hs in tdata.hotspots:
                hp = doc.add_paragraph(f"({hs.label_id}) _______________________")
                hp.paragraph_format.left_indent = Mm((depth + 1) * 7.0)

    # ========================================================================
    # Answer Key & Marking Scheme DOCX Exporters
    # ========================================================================

    @staticmethod
    def export_answer_key_docx(
        project: ProjectState,
        output_path: Path | str,
        overwrite: bool = True,
        dynamic_seed: int = 101,
    ) -> Path:
        """Export a separate editable Answer Key `.docx` document for `project`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".docx":
            dest = dest.with_suffix(".docx")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Answer Key DOCX '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)

        entries = SupplementaryBuilder.extract_answer_key_entries(project, dynamic_seed=dynamic_seed)
        doc = docx.Document()
        DOCXExporter._configure_word_section_and_headers(doc, project)

        meta = project.exam_metadata
        set_suffix = f" ({meta.set_identifier})" if meta.set_identifier else ""
        hdr = doc.add_paragraph()
        hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_h = hdr.add_run(f"OFFICIAL ANSWER KEY{set_suffix} — {meta.exam_name or project.title}")
        r_h.bold = True
        r_h.font.size = Pt(13)

        tbl = doc.add_table(rows=len(entries) + 1, cols=4)
        tbl.style = "Table Grid"
        headers = ("Q. No.", "Type", "Correct Answer / Solution Key", "Marks")
        for idx, h_text in enumerate(headers):
            c = tbl.rows[0].cells[idx]
            c.text = h_text
            for r in c.paragraphs[0].runs:
                r.bold = True

        for r_idx, entry in enumerate(entries, start=1):
            row_cells = tbl.rows[r_idx].cells
            row_cells[0].text = entry.resolved_number
            row_cells[1].text = entry.question_type
            DOCXExporter._append_rich_text_and_omml(
                row_cells[2].paragraphs[0],
                entry.concise_answer_html,
            )
            row_cells[3].text = f"{entry.marks:g}"

        doc.save(str(dest))
        return dest

    @staticmethod
    def export_marking_scheme_docx(
        project: ProjectState,
        output_path: Path | str,
        overwrite: bool = True,
        dynamic_seed: int = 101,
    ) -> Path:
        """Export a separate editable Point-wise Marking Scheme / Rubric `.docx` document."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".docx":
            dest = dest.with_suffix(".docx")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Marking Scheme DOCX '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)

        entries = SupplementaryBuilder.extract_answer_key_entries(project, dynamic_seed=dynamic_seed)
        doc = docx.Document()
        DOCXExporter._configure_word_section_and_headers(doc, project)

        meta = project.exam_metadata
        set_suffix = f" ({meta.set_identifier})" if meta.set_identifier else ""
        hdr = doc.add_paragraph()
        hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_h = hdr.add_run(f"MARKING SCHEME & RUBRIC{set_suffix} — {meta.exam_name or project.title}")
        r_h.bold = True
        r_h.font.size = Pt(13)

        tbl = doc.add_table(rows=len(entries) + 1, cols=5)
        tbl.style = "Table Grid"
        headers = ("Q. No.", "Model Answer", "Step Breakdown", "Rubric Notes / Alternatives", "Marks")
        for idx, h_text in enumerate(headers):
            c = tbl.rows[0].cells[idx]
            c.text = h_text
            for r in c.paragraphs[0].runs:
                r.bold = True

        for r_idx, entry in enumerate(entries, start=1):
            row_cells = tbl.rows[r_idx].cells
            row_cells[0].text = entry.resolved_number
            DOCXExporter._append_rich_text_and_omml(
                row_cells[1].paragraphs[0],
                entry.concise_answer_html,
            )
            row_cells[2].text = "\n".join(entry.step_breakdown) if entry.step_breakdown else "Full credit"
            notes_parts: List[str] = []
            if entry.alternative_answers:
                notes_parts.append("Alt: " + ", ".join(entry.alternative_answers))
            if entry.rubric_notes:
                notes_parts.append(entry.rubric_notes)
            row_cells[3].text = "\n".join(notes_parts) if notes_parts else "—"
            row_cells[4].text = f"{entry.marks:g}"

        doc.save(str(dest))
        return dest
