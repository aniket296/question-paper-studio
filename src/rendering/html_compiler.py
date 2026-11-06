"""Semantic HTML5 Compiler for Question Paper Studio ASTs.

Compiles a `ProjectState` into a self-contained, print-ready HTML5 document with:
- Millimeter-accurate header & footer boxes (`@page` + table header/footer spacing).
- Candidate info fields & general instructions box.
- Watermark overlay when configured.
- Renderers for all 4 core question types and all 9 optional question types.
- Bilingual layouts (Sequential or Side-by-Side) with bundled Noto Sans Devanagari.
- Strict page-break protection (`break-inside: avoid;`, `break-after: avoid;`).
- Offline LaTeX-to-MathML conversion for `$...$` and `$$...$$` equations.
- Student-facing mode (hides correct answers/rubrics) vs Teacher Preview mode.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import latex2mathml.converter

from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import NumberingFSM
from src.core.models.enums import (
    BilingualLayout,
    CanvasElementType,
    ChoiceRuleType,
    FillBlankMode,
    MCQOptionLayout,
    MarksPosition,
    QuestionType,
)
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    AssertionReasonData,
    CaseBasedData,
    DiagramAttachment,
    DiagramLabellingData,
    FillBlankData,
    LongAnswerData,
    MCQData,
    MatchPairData,
    NumericalDynamicData,
    OrderingSequencingData,
    QuestionNode,
    ShortAnswerData,
    SourceBasedData,
    TrueFalseData,
)
from src.core.models.section_model import ChoiceGroup, Section, SharedPassage
from src.core.models.template_model import CanvasElement, Template
from src.rendering.css_generator import CSSGenerator

_BLOCK_LATEX_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_LATEX_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")


def convert_latex_in_html_to_mathml(rich_html: str) -> str:
    """Convert inline `$...$` and display `$$...$$` LaTeX expressions into offline MathML."""
    if "$" not in rich_html:
        return rich_html

    def _replace_block(match: re.Match[str]) -> str:
        expr = html.unescape(match.group(1).strip())
        try:
            return latex2mathml.converter.convert(expr, display="block")
        except Exception:
            return f'<span class="math-fallback">{html.escape(expr)}</span>'

    def _replace_inline(match: re.Match[str]) -> str:
        expr = html.unescape(match.group(1).strip())
        try:
            return latex2mathml.converter.convert(expr, display="inline")
        except Exception:
            return f'<span class="math-fallback">{html.escape(expr)}</span>'

    out = _BLOCK_LATEX_RE.sub(_replace_block, rich_html)
    out = _INLINE_LATEX_RE.sub(_replace_inline, out)
    return out


def _asset_to_src_uri(asset_path: str, base_dir: Optional[Path] = None) -> str:
    """Resolve an image path to a `data:` URI or `file://` URI so offline rendering works anywhere."""
    if not asset_path:
        return ""
    if asset_path.startswith(("data:", "http://", "https://", "file://")):
        return asset_path

    candidate = Path(asset_path)
    if not candidate.is_absolute() and base_dir is not None:
        candidate = (base_dir / asset_path).resolve()

    if candidate.exists() and candidate.is_file():
        mime_type, _ = mimetypes.guess_type(str(candidate))
        mime = mime_type or "image/png"
        try:
            b64 = base64.b64encode(candidate.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return candidate.resolve().as_uri()
    return asset_path


def _format_marks_badge(marks: Optional[float]) -> str:
    if marks is None or marks <= 0:
        return ""
    val_str = str(int(marks)) if float(marks).is_integer() else f"{marks:g}"
    return f"[{val_str}]"


class HTMLCompiler:
    """Compiles a `ProjectState` AST into semantic, print-ready HTML5."""

    @staticmethod
    def compile_project(
        project: ProjectState,
        teacher_preview_mode: bool = False,
        preview_sheet_framing: bool = False,
        base_asset_dir: Optional[Path] = None,
        dynamic_seed: int = 101,
    ) -> str:
        """Compile `project` into a complete HTML5 document string."""
        NumberingFSM.resolve_project(project)
        marks_report = MarksEngine.audit_project_marks(project)

        # Ensure max_marks placeholder reflects either explicit max_marks or computed effective total
        placeholder_ctx = project.exam_metadata.to_placeholder_context(
            page_number="1",
            total_pages="1",
        )
        if not placeholder_ctx["{{max_marks}}"] and marks_report.total_effective_marks > 0:
            eff = marks_report.total_effective_marks
            placeholder_ctx["{{max_marks}}"] = str(int(eff)) if float(eff).is_integer() else f"{eff:g}"

        stylesheet = CSSGenerator.generate_stylesheet(
            project,
            preview_sheet_framing=preview_sheet_framing,
        )

        template = project.template_snapshot
        header_html = HTMLCompiler._render_template_zone(
            elements=template.get_header_elements(is_first_page=True),
            placeholder_ctx=placeholder_ctx,
            zone_class="template-header-box",
            base_asset_dir=base_asset_dir,
        )
        footer_html = HTMLCompiler._render_template_zone(
            elements=template.get_footer_elements(is_first_page=True),
            placeholder_ctx=placeholder_ctx,
            zone_class="template-footer-box",
            base_asset_dir=base_asset_dir,
        )

        watermark_html = ""
        if project.exam_metadata.watermark_text and project.exam_metadata.watermark_text.strip():
            wm = html.escape(project.exam_metadata.watermark_text.strip())
            watermark_html = f'<div class="watermark-overlay">{wm}</div>'

        candidate_box_html = HTMLCompiler._render_candidate_box(project)
        instructions_html = HTMLCompiler._render_general_instructions(project)

        sections_html_parts: List[str] = []
        for section in project.sections:
            sections_html_parts.append(
                HTMLCompiler._render_section(
                    project=project,
                    section=section,
                    teacher_preview_mode=teacher_preview_mode,
                    base_asset_dir=base_asset_dir,
                    dynamic_seed=dynamic_seed,
                )
            )
        sections_joined = "\n".join(sections_html_parts)

        title_escaped = html.escape(project.title)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title_escaped}</title>
<style>
{stylesheet}
</style>
</head>
<body>
{watermark_html}
<div class="paper-document">
    <header class="paper-header-region">
        {header_html}
    </header>
    {candidate_box_html}
    {instructions_html}
    <main class="paper-body-region">
        {sections_joined}
    </main>
    <footer class="paper-footer-region">
        {footer_html}
    </footer>
</div>
</body>
</html>
"""

    @staticmethod
    def _render_template_zone(
        elements: List[CanvasElement],
        placeholder_ctx: Dict[str, str],
        zone_class: str,
        base_asset_dir: Optional[Path] = None,
    ) -> str:
        parts: List[str] = [f'<div class="{zone_class}">']
        for el in elements:
            style_tokens = [
                f"left: {el.x_mm:.2f}mm",
                f"top: {el.y_mm:.2f}mm",
                f"width: {el.width_mm:.2f}mm",
                f"height: {el.height_mm:.2f}mm",
                f"font-family: '{el.font_family}', 'Noto Sans', 'Noto Sans Devanagari', sans-serif",
                f"font-size: {el.font_size_pt:.1f}pt",
                f"text-align: {el.alignment.value}",
                f"color: {el.color_hex}",
            ]
            if el.bold:
                style_tokens.append("font-weight: 700")
            if el.italic:
                style_tokens.append("font-style: italic")
            if el.underline:
                style_tokens.append("text-decoration: underline")

            if el.element_type == CanvasElementType.LINE:
                style_tokens.append(f"border-bottom: {el.line_thickness_pt:.2f}pt solid {el.color_hex}")
                parts.append(f'<div class="canvas-element" style="{"; ".join(style_tokens)}"></div>')
            elif el.element_type == CanvasElementType.BORDER:
                style_tokens.append(f"border: {el.line_thickness_pt:.2f}pt solid {el.color_hex}")
                parts.append(f'<div class="canvas-element" style="{"; ".join(style_tokens)}"></div>')
            elif el.element_type == CanvasElementType.IMAGE:
                src = _asset_to_src_uri(el.content, base_dir=base_asset_dir)
                parts.append(
                    f'<div class="canvas-element" style="{"; ".join(style_tokens)}">'
                    f'<img src="{html.escape(src)}" alt="Header Logo" '
                    f'style="max-width: 100%; max-height: 100%; object-fit: contain;" />'
                    f"</div>"
                )
            else:
                # TEXT or PAGE_NUMBER
                rendered_text = el.render_placeholders(placeholder_ctx)
                parts.append(
                    f'<div class="canvas-element" style="{"; ".join(style_tokens)}">'
                    f"{html.escape(rendered_text)}"
                    f"</div>"
                )
        parts.append("</div>")
        return "\n".join(parts)

    @staticmethod
    def _render_candidate_box(project: ProjectState) -> str:
        fields = project.exam_metadata.candidate_fields
        if not fields:
            return ""

        cells: List[str] = []
        for cf in fields:
            cells.append(f"<td>{html.escape(cf.value)}: ________________________</td>")

        rows: List[str] = []
        for i in range(0, len(cells), 2):
            pair = cells[i : i + 2]
            if len(pair) == 1:
                pair.append("<td></td>")
            rows.append(f"<tr>{''.join(pair)}</tr>")

        return f'<table class="candidate-info-box">{"".join(rows)}</table>'

    @staticmethod
    def _render_general_instructions(project: ProjectState) -> str:
        instr = project.exam_metadata.general_instructions.strip()
        if not instr:
            return ""
        math_instr = convert_latex_in_html_to_mathml(instr)
        return (
            '<div class="general-instructions-box">'
            '<div class="general-instructions-title">General Instructions:</div>'
            f'<div class="general-instructions-content">{math_instr}</div>'
            "</div>"
        )

    @staticmethod
    def _render_section(
        project: ProjectState,
        section: Section,
        teacher_preview_mode: bool,
        base_asset_dir: Optional[Path],
        dynamic_seed: int,
    ) -> str:
        cols = section.columns_override or project.layout_settings.columns
        parts: List[str] = [f'<section class="section-container columns-{cols}">']

        if not section.is_default_unsectioned:
            parts.append('<div class="section-header">')
            parts.append(f'<div class="section-title">{html.escape(section.title)}</div>')
            if section.instructions_html.strip():
                parts.append(
                    f'<div class="section-instructions">'
                    f"{convert_latex_in_html_to_mathml(section.instructions_html)}"
                    f"</div>"
                )
            elif section.attempt_any_k is not None:
                parts.append(
                    f'<div class="section-instructions">'
                    f"Attempt any {section.attempt_any_k} out of {len(section.questions)} questions."
                    f"</div>"
                )
            parts.append("</div>")

        # Map question_id -> SharedPassage and ChoiceGroup
        passage_by_first_qid: Dict[str, SharedPassage] = {}
        passage_by_id: Dict[str, SharedPassage] = {}
        for sp in section.shared_passages:
            passage_by_id[sp.passage_id] = sp
            if sp.linked_question_ids:
                passage_by_first_qid[sp.linked_question_ids[0]] = sp

        rendered_passages: Set[str] = set()

        # Map ChoiceGroup rules
        or_after_qid: Dict[str, str] = {}
        any_k_banner_before_qid: Dict[str, str] = {}
        for cg in section.choice_groups:
            if not cg.question_ids:
                continue
            if cg.rule_type == ChoiceRuleType.OR_PAIR and len(cg.question_ids) >= 2:
                for qid in cg.question_ids[:-1]:
                    or_after_qid[qid] = cg.label_text or "OR"
            elif cg.rule_type == ChoiceRuleType.ANY_K_OF_N:
                first_id = cg.question_ids[0]
                any_k_banner_before_qid[first_id] = (
                    f"Answer any {cg.attempt_count_k} of the following {len(cg.question_ids)} questions:"
                )

        for q in section.questions:
            # Render shared passage immediately before the first question that references it
            sp_candidate = passage_by_first_qid.get(q.question_id)
            if sp_candidate is None and q.shared_passage_id in passage_by_id:
                sp_candidate = passage_by_id[q.shared_passage_id]

            if sp_candidate is not None and sp_candidate.passage_id not in rendered_passages:
                rendered_passages.add(sp_candidate.passage_id)
                parts.append(
                    HTMLCompiler._render_shared_passage(
                        project=project,
                        passage=sp_candidate,
                        base_asset_dir=base_asset_dir,
                    )
                )

            if q.question_id in any_k_banner_before_qid:
                banner_txt = html.escape(any_k_banner_before_qid[q.question_id])
                parts.append(f'<div class="choice-group-banner">{banner_txt}</div>')

            parts.append(
                HTMLCompiler._render_question_node(
                    project=project,
                    node=q,
                    teacher_preview_mode=teacher_preview_mode,
                    base_asset_dir=base_asset_dir,
                    dynamic_seed=dynamic_seed,
                )
            )

            if q.question_id in or_after_qid:
                or_lbl = html.escape(or_after_qid[q.question_id])
                parts.append(f'<div class="or-divider">— {or_lbl} —</div>')

        parts.append("</section>")
        return "\n".join(parts)

    @staticmethod
    def _render_shared_passage(
        project: ProjectState,
        passage: SharedPassage,
        base_asset_dir: Optional[Path],
    ) -> str:
        parts: List[str] = ['<div class="shared-passage-block">']
        if passage.instruction_text.strip():
            parts.append(
                f'<div class="shared-passage-instruction">'
                f"{html.escape(passage.instruction_text)}"
                f"</div>"
            )
        if passage.title.strip():
            parts.append(f"<div><strong>{html.escape(passage.title)}</strong></div>")

        primary_html = convert_latex_in_html_to_mathml(passage.content_html)
        if project.layout_settings.bilingual_mode and passage.content_secondary_html:
            sec_html = convert_latex_in_html_to_mathml(passage.content_secondary_html)
            if project.layout_settings.bilingual_layout == BilingualLayout.SIDE_BY_SIDE:
                parts.append(
                    f'<div class="bilingual-side-by-side">'
                    f"<div>{primary_html}</div>"
                    f'<div class="secondary-lang-block">{sec_html}</div>'
                    f"</div>"
                )
            else:
                parts.append(
                    f'<div class="bilingual-sequential">'
                    f"<div>{primary_html}</div>"
                    f'<div class="secondary-lang-block">{sec_html}</div>'
                    f"</div>"
                )
        else:
            parts.append(f"<div>{primary_html}</div>")

        for diag in passage.diagrams:
            parts.append(HTMLCompiler._render_diagram(diag, base_asset_dir=base_asset_dir))

        parts.append("</div>")
        return "\n".join(parts)

    @staticmethod
    def _render_diagram(
        diag: DiagramAttachment,
        base_asset_dir: Optional[Path],
    ) -> str:
        src = _asset_to_src_uri(diag.asset_path, base_dir=base_asset_dir)
        align = diag.alignment.value
        caption_html = (
            f'<div class="diagram-caption">{html.escape(diag.caption)}</div>'
            if diag.caption.strip()
            else ""
        )
        return (
            f'<div class="diagram-container" style="text-align: {align};">'
            f'<img src="{html.escape(src)}" alt="Diagram" '
            f'style="width: {diag.width_mm:.1f}mm; height: {diag.height_mm:.1f}mm; object-fit: contain;" />'
            f"{caption_html}"
            f"</div>"
        )

    @staticmethod
    def _render_question_node(
        project: ProjectState,
        node: QuestionNode,
        teacher_preview_mode: bool,
        base_asset_dir: Optional[Path],
        dynamic_seed: int,
    ) -> str:
        layout = project.layout_settings
        q_summary = MarksEngine.calculate_question_effective_marks(node)
        effective_marks = q_summary.effective_marks if layout.show_marks else None
        marks_str = _format_marks_badge(effective_marks)

        pb_class = " force-page-break" if node.page_break_before else ""
        parts: List[str] = [
            f'<div class="question-block{pb_class}" data-question-id="{html.escape(node.question_id)}">'
        ]

        # Prepare prompt text (handling Dynamic Numerical variable instantiation if applicable)
        raw_prompt = node.prompt_html
        dynamic_ans_badge = ""
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
                if inst.computed_answer is not None:
                    dynamic_ans_badge = f"{inst.formatted_answer} {inst.unit}".strip()

        primary_prompt = convert_latex_in_html_to_mathml(raw_prompt)
        if (
            layout.show_marks
            and layout.marks_position == MarksPosition.INLINE_END
            and marks_str
        ):
            primary_prompt += f'<span class="question-marks-inline">{marks_str}</span>'

        if layout.bilingual_mode and node.prompt_secondary_html:
            secondary_prompt = convert_latex_in_html_to_mathml(node.prompt_secondary_html)
            if layout.bilingual_layout == BilingualLayout.SIDE_BY_SIDE:
                prompt_combined = (
                    f'<div class="bilingual-side-by-side">'
                    f"<div>{primary_prompt}</div>"
                    f'<div class="secondary-lang-block">{secondary_prompt}</div>'
                    f"</div>"
                )
            else:
                prompt_combined = (
                    f'<div class="bilingual-sequential">'
                    f"<div>{primary_prompt}</div>"
                    f'<div class="secondary-lang-block">{secondary_prompt}</div>'
                    f"</div>"
                )
        else:
            prompt_combined = primary_prompt

        type_body_html = HTMLCompiler._render_question_type_payload(
            node=node,
            teacher_preview_mode=teacher_preview_mode,
            base_asset_dir=base_asset_dir,
            dynamic_ans_badge=dynamic_ans_badge,
        )

        diagrams_html = "\n".join(
            HTMLCompiler._render_diagram(d, base_asset_dir=base_asset_dir)
            for d in node.diagrams
        )

        answer_lines_html = ""
        if node.answer_space_lines > 0:
            lines = "".join('<div class="answer-line"></div>' for _ in range(node.answer_space_lines))
            answer_lines_html = f'<div class="answer-space-lines">{lines}</div>'

        right_marks_cell = (
            f'<div class="question-marks-right">{marks_str}</div>'
            if (layout.show_marks and layout.marks_position == MarksPosition.RIGHT_MARGIN and marks_str)
            else ""
        )

        parts.append('<div class="question-row">')
        parts.append(f'<div class="question-number">{html.escape(node.resolved_number)}</div>')
        parts.append('<div class="question-content">')
        parts.append(prompt_combined)
        if diagrams_html:
            parts.append(diagrams_html)
        if type_body_html:
            parts.append(type_body_html)
        if answer_lines_html:
            parts.append(answer_lines_html)
        parts.append("</div>")
        if right_marks_cell:
            parts.append(right_marks_cell)
        parts.append("</div>")

        if node.children:
            parts.append('<div class="subquestions-container">')
            for child in node.children:
                parts.append(
                    HTMLCompiler._render_question_node(
                        project=project,
                        node=child,
                        teacher_preview_mode=teacher_preview_mode,
                        base_asset_dir=base_asset_dir,
                        dynamic_seed=dynamic_seed,
                    )
                )
            parts.append("</div>")

        parts.append("</div>")
        return "\n".join(parts)

    @staticmethod
    def _render_question_type_payload(
        node: QuestionNode,
        teacher_preview_mode: bool,
        base_asset_dir: Optional[Path],
        dynamic_ans_badge: str = "",
    ) -> str:
        parts: List[str] = []
        tdata = node.type_data

        # 1. MCQ
        if node.question_type == QuestionType.MCQ and isinstance(tdata, MCQData):
            if tdata.option_layout == MCQOptionLayout.INLINE:
                layout_cls = "mcq-options-inline"
            elif tdata.option_layout == MCQOptionLayout.STACKED:
                layout_cls = "mcq-options-stacked"
            else:
                layout_cls = "mcq-options-grid-2x2"

            parts.append(f'<div class="{layout_cls}">')
            correct_labels: List[str] = []
            for opt in tdata.options:
                opt_html = convert_latex_in_html_to_mathml(opt.text_html)
                if opt.is_correct:
                    correct_labels.append(opt.label)
                parts.append(
                    f'<div class="mcq-option-item">'
                    f'<span class="mcq-option-label">({html.escape(opt.label)})</span>'
                    f'<span class="mcq-option-text">{opt_html}</span>'
                    f"</div>"
                )
            parts.append("</div>")
            if teacher_preview_mode and correct_labels:
                parts.append(
                    f'<div class="teacher-key-badge">'
                    f"<strong>Answer Key:</strong> Option {', '.join(correct_labels)}"
                    f"</div>"
                )

        # 2. Fill in the Blank
        elif node.question_type == QuestionType.FILL_IN_THE_BLANK and isinstance(tdata, FillBlankData):
            if tdata.mode == FillBlankMode.WITH_OPTIONS and tdata.word_bank_options:
                opts_escaped = [html.escape(w) for w in tdata.word_bank_options]
                parts.append(
                    f'<div class="word-bank-box">'
                    f"<strong>Options:</strong> ( {' / '.join(opts_escaped)} )"
                    f"</div>"
                )
            if teacher_preview_mode:
                ans_items = [
                    f"({b.blank_index}) {html.escape(b.correct_answer)}"
                    for b in tdata.blanks
                    if b.correct_answer.strip()
                ]
                if ans_items:
                    parts.append(
                        f'<div class="teacher-key-badge">'
                        f"<strong>Answer Key:</strong> {', '.join(ans_items)}"
                        f"</div>"
                    )

        # 3. Match the Pair
        elif node.question_type == QuestionType.MATCH_THE_PAIR and isinstance(tdata, MatchPairData):
            parts.append('<table class="match-pair-table">')
            parts.append(
                f"<thead><tr>"
                f"<th>{html.escape(tdata.col_a_header)}</th>"
                f"<th>{html.escape(tdata.col_b_header)}</th>"
                f"</tr></thead><tbody>"
            )
            # Determine displayed Column B order
            col_b_by_display_pos: Dict[int, str] = {}
            for idx, r in enumerate(tdata.rows):
                disp_idx = r.shuffled_col_b_index if r.shuffled_col_b_index is not None else idx
                col_b_by_display_pos[disp_idx] = r.col_b_html

            for idx, r in enumerate(tdata.rows):
                col_a = convert_latex_in_html_to_mathml(r.col_a_html)
                col_b = convert_latex_in_html_to_mathml(col_b_by_display_pos.get(idx, r.col_b_html))
                roman_lbl = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")[idx % 10]
                alpha_lbl = chr(ord("A") + (idx % 26))
                parts.append(
                    f"<tr>"
                    f"<td>({roman_lbl}) {col_a}</td>"
                    f"<td>({alpha_lbl}) {col_b}</td>"
                    f"</tr>"
                )
            parts.append("</tbody></table>")
            if teacher_preview_mode:
                gt = tdata.ground_truth_mapping()
                pairs_str = ", ".join(
                    f"({k}) → ({chr(ord('A') + v - 1)})" for k, v in sorted(gt.items())
                )
                parts.append(
                    f'<div class="teacher-key-badge">'
                    f"<strong>Answer Key:</strong> {pairs_str}"
                    f"</div>"
                )

        # 4. True / False
        elif node.question_type == QuestionType.TRUE_FALSE and isinstance(tdata, TrueFalseData):
            just_note = " (State reason)" if tdata.require_justification else ""
            parts.append(f'<div class="word-bank-box">[ True / False ]{just_note}</div>')
            if teacher_preview_mode and tdata.correct_is_true is not None:
                val_str = "True" if tdata.correct_is_true else "False"
                parts.append(
                    f'<div class="teacher-key-badge"><strong>Answer Key:</strong> {val_str}</div>'
                )

        # 5. Assertion & Reason
        elif node.question_type == QuestionType.ASSERTION_REASON and isinstance(tdata, AssertionReasonData):
            a_html = convert_latex_in_html_to_mathml(tdata.assertion_html)
            r_html = convert_latex_in_html_to_mathml(tdata.reason_html)
            parts.append(
                f'<div style="margin-top: 1.5mm;">'
                f"<div><strong>Assertion (A):</strong> {a_html}</div>"
                f"<div><strong>Reason (R):</strong> {r_html}</div>"
                f"</div>"
            )
            parts.append('<div class="mcq-options-stacked">')
            for idx, opt_str in enumerate(tdata.options):
                lbl = chr(ord("A") + idx)
                parts.append(
                    f'<div class="mcq-option-item">'
                    f'<span class="mcq-option-label">({lbl})</span>'
                    f"<span>{html.escape(opt_str)}</span>"
                    f"</div>"
                )
            parts.append("</div>")
            if teacher_preview_mode:
                corr_lbl = chr(ord("A") + tdata.correct_option_index)
                parts.append(
                    f'<div class="teacher-key-badge"><strong>Answer Key:</strong> Option ({corr_lbl})</div>'
                )

        # 6. Case-Based
        elif node.question_type == QuestionType.CASE_BASED and isinstance(tdata, CaseBasedData):
            if tdata.case_passage_html.strip():
                c_title = f"<strong>{html.escape(tdata.case_title)}</strong><br/>" if tdata.case_title else ""
                c_body = convert_latex_in_html_to_mathml(tdata.case_passage_html)
                parts.append(f'<div class="shared-passage-block">{c_title}{c_body}</div>')

        # 7. Source-Based
        elif node.question_type == QuestionType.SOURCE_BASED and isinstance(tdata, SourceBasedData):
            if tdata.source_excerpt_html.strip():
                s_body = convert_latex_in_html_to_mathml(tdata.source_excerpt_html)
                cit = (
                    f'<div style="text-align: right; font-style: italic; font-size: 9pt;">— {html.escape(tdata.source_citation)}</div>'
                    if tdata.source_citation
                    else ""
                )
                parts.append(f'<div class="shared-passage-block">{s_body}{cit}</div>')

        # 8. Ordering / Sequencing
        elif node.question_type == QuestionType.ORDERING_SEQUENCING and isinstance(tdata, OrderingSequencingData):
            parts.append('<div class="mcq-options-stacked">')
            for idx, item in enumerate(tdata.items, start=1):
                parts.append(
                    f'<div class="mcq-option-item">'
                    f'<span class="mcq-option-label">({idx})</span>'
                    f"<span>{convert_latex_in_html_to_mathml(item.text_html)}</span>"
                    f"</div>"
                )
            parts.append("</div>")
            if teacher_preview_mode and tdata.items:
                sorted_items = sorted(tdata.items, key=lambda x: x.correct_position)
                seq_str = " → ".join(strip_p(i.text_html) for i in sorted_items)
                parts.append(
                    f'<div class="teacher-key-badge"><strong>Correct Sequence:</strong> {html.escape(seq_str)}</div>'
                )

        # 9. Diagram Labelling
        elif node.question_type == QuestionType.DIAGRAM_LABELLING and isinstance(tdata, DiagramLabellingData):
            if tdata.diagram_asset_path:
                src = _asset_to_src_uri(tdata.diagram_asset_path, base_dir=base_asset_dir)
                parts.append(
                    f'<div class="diagram-container">'
                    f'<img src="{html.escape(src)}" alt="Labelling Diagram" style="max-width: 120mm;" />'
                    f"</div>"
                )
            if tdata.hotspots:
                parts.append('<div class="mcq-options-grid-2x2">')
                for hs in tdata.hotspots:
                    parts.append(f"<div><strong>({html.escape(hs.label_id)})</strong> _______________</div>")
                parts.append("</div>")
                if teacher_preview_mode:
                    hs_ans = ", ".join(
                        f"({html.escape(h.label_id)}) {html.escape(h.correct_term)}"
                        for h in tdata.hotspots
                    )
                    parts.append(
                        f'<div class="teacher-key-badge"><strong>Labels:</strong> {hs_ans}</div>'
                    )

        # 10. Dynamic Numerical answer badge in Teacher Preview
        elif node.question_type == QuestionType.NUMERICAL_DYNAMIC and isinstance(tdata, NumericalDynamicData):
            if teacher_preview_mode and (dynamic_ans_badge or tdata.computed_answer is not None):
                ans_disp = dynamic_ans_badge or f"{tdata.computed_answer} {tdata.unit}".strip()
                parts.append(
                    f'<div class="teacher-key-badge">'
                    f"<strong>Computed Answer:</strong> {html.escape(ans_disp)} (±{tdata.answer_tolerance})"
                    f"</div>"
                )

        # 11. Short / Long / Normal model answer or rubric in Teacher Preview
        if teacher_preview_mode and node.marking_scheme is not None:
            ms = node.marking_scheme
            if ms.model_answer_html.strip():
                parts.append(
                    f'<div class="teacher-key-badge">'
                    f"<strong>Model Answer:</strong> {convert_latex_in_html_to_mathml(ms.model_answer_html)}"
                    f"</div>"
                )
            if ms.step_points:
                steps_str = " | ".join(
                    f"{html.escape(sp.description)} ({sp.marks:g}M)" for sp in ms.step_points
                )
                parts.append(
                    f'<div class="teacher-key-badge">'
                    f"<strong>Marking Scheme:</strong> {steps_str}"
                    f"</div>"
                )

        return "\n".join(parts)


def strip_p(raw_html: str) -> str:
    return re.sub(r"<[^>]+>", "", raw_html).strip()
