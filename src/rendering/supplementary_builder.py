"""Supplementary Document Builder: Separate Answer Keys, Marking Rubrics, and Candidate/OMR Answer Sheets."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import List, Optional

from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import NumberingFSM
from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    AssertionReasonData,
    DiagramLabellingData,
    FillBlankData,
    MCQData,
    MatchPairData,
    NumericalDynamicData,
    OrderingSequencingData,
    QuestionNode,
    TrueFalseData,
)
from src.rendering.css_generator import CSSGenerator
from src.rendering.html_compiler import convert_latex_in_html_to_mathml, strip_p


@dataclass
class AnswerKeyEntry:
    """Structured answer key row for a single question or subquestion."""

    question_id: str
    resolved_number: str
    question_type: str
    marks: float
    concise_answer_html: str
    step_breakdown: List[str]
    alternative_answers: List[str]
    rubric_notes: str


class SupplementaryBuilder:
    """Extracts and compiles Answer Keys, Marking Schemes/Rubrics, and Candidate/OMR Answer Sheets."""

    @staticmethod
    def extract_answer_key_entries(
        project: ProjectState,
        dynamic_seed: int = 101,
    ) -> List[AnswerKeyEntry]:
        """Extract ordered `AnswerKeyEntry` records across all questions and subquestions in `project`."""
        NumberingFSM.resolve_project(project)
        entries: List[AnswerKeyEntry] = []

        for q in project.all_questions_dfs():
            q_sum = MarksEngine.calculate_question_effective_marks(q)
            tdata = q.type_data
            ans_str = ""

            if q.question_type == QuestionType.MCQ and isinstance(tdata, MCQData):
                correct_opts = [
                    f"({opt.label}) {strip_p(opt.text_html)}"
                    for opt in tdata.options
                    if opt.is_correct
                ]
                ans_str = ", ".join(correct_opts) if correct_opts else "No correct option marked"

            elif q.question_type == QuestionType.FILL_IN_THE_BLANK and isinstance(tdata, FillBlankData):
                ans_str = ", ".join(
                    f"({b.blank_index}) {b.correct_answer}"
                    for b in tdata.blanks
                    if b.correct_answer.strip()
                )

            elif q.question_type == QuestionType.MATCH_THE_PAIR and isinstance(tdata, MatchPairData):
                gt = tdata.ground_truth_mapping()
                ans_str = ", ".join(
                    f"({k}) → ({chr(ord('A') + v - 1)})" for k, v in sorted(gt.items())
                )

            elif q.question_type == QuestionType.TRUE_FALSE and isinstance(tdata, TrueFalseData):
                if tdata.correct_is_true is not None:
                    ans_str = "True" if tdata.correct_is_true else "False"

            elif q.question_type == QuestionType.ASSERTION_REASON and isinstance(tdata, AssertionReasonData):
                lbl = chr(ord("A") + tdata.correct_option_index)
                ans_str = f"Option ({lbl})"

            elif q.question_type == QuestionType.NUMERICAL_DYNAMIC and isinstance(tdata, NumericalDynamicData):
                if tdata.variables and tdata.formula_expr.strip():
                    inst = DynamicNumericEngine.instantiate_question(
                        q.prompt_html,
                        tdata,
                        seed=dynamic_seed,
                    )
                    ans_str = f"{inst.formatted_answer} {inst.unit} (±{inst.tolerance})".strip()
                elif tdata.computed_answer is not None:
                    ans_str = f"{tdata.computed_answer} {tdata.unit}".strip()

            elif q.question_type == QuestionType.ORDERING_SEQUENCING and isinstance(tdata, OrderingSequencingData):
                sorted_items = sorted(tdata.items, key=lambda x: x.correct_position)
                ans_str = " → ".join(strip_p(i.text_html) for i in sorted_items)

            elif q.question_type == QuestionType.DIAGRAM_LABELLING and isinstance(tdata, DiagramLabellingData):
                ans_str = ", ".join(f"({h.label_id}) {h.correct_term}" for h in tdata.hotspots)

            steps: List[str] = []
            alt_answers: List[str] = []
            rubric_notes = ""

            if q.marking_scheme is not None:
                ms = q.marking_scheme
                if not ans_str and ms.model_answer_html.strip():
                    ans_str = convert_latex_in_html_to_mathml(ms.model_answer_html)
                steps = [f"{sp.description} [{sp.marks:g}M]" for sp in ms.step_points]
                alt_answers = list(ms.alternative_answers)
                rubric_notes = ms.rubric_notes

            if not ans_str and q.children:
                ans_str = "<em>(See subquestions below)</em>"

            entries.append(
                AnswerKeyEntry(
                    question_id=q.question_id,
                    resolved_number=q.resolved_number,
                    question_type=q.question_type.value,
                    marks=q_sum.effective_marks,
                    concise_answer_html=ans_str or "<em>—</em>",
                    step_breakdown=steps,
                    alternative_answers=alt_answers,
                    rubric_notes=rubric_notes,
                )
            )
        return entries

    @staticmethod
    def compile_answer_key_html(
        project: ProjectState,
        dynamic_seed: int = 101,
    ) -> str:
        """Generate a clean, print-ready Answer Key HTML5 document."""
        entries = SupplementaryBuilder.extract_answer_key_entries(project, dynamic_seed=dynamic_seed)
        stylesheet = CSSGenerator.generate_stylesheet(project)
        meta = project.exam_metadata
        set_badge = f" — {html.escape(meta.set_identifier)}" if meta.set_identifier else ""
        title_str = html.escape(meta.exam_name or project.title)

        rows_html: List[str] = []
        for e in entries:
            rows_html.append(
                f"<tr>"
                f"<td><strong>{html.escape(e.resolved_number)}</strong></td>"
                f"<td>{html.escape(e.question_type)}</td>"
                f"<td>{e.concise_answer_html}</td>"
                f"<td style='text-align: right;'>{e.marks:g}</td>"
                f"</tr>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Answer Key — {title_str}{set_badge}</title>
<style>
{stylesheet}
</style>
</head>
<body>
<div class="paper-document">
    <div class="section-header">
        <div class="section-title">OFFICIAL ANSWER KEY{set_badge}</div>
        <div>{title_str} | {html.escape(meta.subject_name)}</div>
    </div>
    <table class="match-pair-table">
        <thead>
            <tr>
                <th style="width: 14%;">Q. No.</th>
                <th style="width: 20%;">Type</th>
                <th style="width: 52%;">Correct Answer / Solution Key</th>
                <th style="width: 14%; text-align: right;">Marks</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
</div>
</body>
</html>
"""

    @staticmethod
    def compile_marking_scheme_html(
        project: ProjectState,
        dynamic_seed: int = 101,
    ) -> str:
        """Generate a detailed Point-Wise Marking Scheme & Evaluation Rubric HTML5 document."""
        entries = SupplementaryBuilder.extract_answer_key_entries(project, dynamic_seed=dynamic_seed)
        stylesheet = CSSGenerator.generate_stylesheet(project)
        meta = project.exam_metadata
        set_badge = f" — {html.escape(meta.set_identifier)}" if meta.set_identifier else ""
        title_str = html.escape(meta.exam_name or project.title)

        rows_html: List[str] = []
        for e in entries:
            steps_html = (
                "<ul>" + "".join(f"<li>{html.escape(s)}</li>" for s in e.step_breakdown) + "</ul>"
                if e.step_breakdown
                else "<em>Full credit for complete correct response</em>"
            )
            notes_parts: List[str] = []
            if e.alternative_answers:
                notes_parts.append(
                    "<strong>Alternatives:</strong> " + ", ".join(html.escape(a) for a in e.alternative_answers)
                )
            if e.rubric_notes:
                notes_parts.append("<strong>Notes:</strong> " + html.escape(e.rubric_notes))
            notes_html = "<br/>".join(notes_parts) if notes_parts else "—"

            rows_html.append(
                f"<tr>"
                f"<td><strong>{html.escape(e.resolved_number)}</strong></td>"
                f"<td>{e.concise_answer_html}</td>"
                f"<td>{steps_html}</td>"
                f"<td>{notes_html}</td>"
                f"<td style='text-align: right;'>{e.marks:g}</td>"
                f"</tr>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Marking Scheme & Rubric — {title_str}{set_badge}</title>
<style>
{stylesheet}
</style>
</head>
<body>
<div class="paper-document">
    <div class="section-header">
        <div class="section-title">MARKING SCHEME & EVALUATION RUBRIC{set_badge}</div>
        <div>{title_str} | {html.escape(meta.subject_name)}</div>
    </div>
    <table class="match-pair-table">
        <thead>
            <tr>
                <th style="width: 10%;">Q. No.</th>
                <th style="width: 34%;">Model Answer</th>
                <th style="width: 28%;">Step-wise Marks Breakdown</th>
                <th style="width: 18%;">Rubric Notes / Alternatives</th>
                <th style="width: 10%; text-align: right;">Marks</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
</div>
</body>
</html>
"""

    @staticmethod
    def compile_candidate_omr_sheet_html(project: ProjectState) -> str:
        """Generate a separate Candidate Response / OMR Bubble & Answer Sheet HTML5 document."""
        NumberingFSM.resolve_project(project)
        stylesheet = CSSGenerator.generate_stylesheet(project)
        meta = project.exam_metadata
        title_str = html.escape(meta.exam_name or project.title)

        rows_html: List[str] = []
        for q in project.all_questions_dfs():
            if q.children:
                continue
            tdata = q.type_data
            if q.question_type == QuestionType.MCQ and isinstance(tdata, MCQData):
                bubbles = " &nbsp;&nbsp; ".join(
                    f"&#9711; <strong>{html.escape(opt.label)}</strong>" for opt in tdata.options
                )
                response_space = f'<div style="font-size: 11pt;">{bubbles}</div>'
            elif q.question_type == QuestionType.TRUE_FALSE:
                response_space = '<div>&#9711; <strong>True</strong> &nbsp;&nbsp;&nbsp; &#9711; <strong>False</strong></div>'
            else:
                line_count = max(2, q.answer_space_lines or 2)
                lines = "".join('<div class="answer-line"></div>' for _ in range(line_count))
                response_space = f'<div class="answer-space-lines">{lines}</div>'

            rows_html.append(
                f"<tr>"
                f"<td style='width: 14%;'><strong>{html.escape(q.resolved_number)}</strong></td>"
                f"<td style='width: 74%;'>{response_space}</td>"
                f"<td style='width: 12%; text-align: right;'>[ &nbsp;&nbsp; / {q.marks or 0:g} ]</td>"
                f"</tr>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Candidate Answer & OMR Sheet — {title_str}</title>
<style>
{stylesheet}
</style>
</head>
<body>
<div class="paper-document">
    <div class="section-header">
        <div class="section-title">CANDIDATE RESPONSE & OMR SHEET</div>
        <div>{title_str} | {html.escape(meta.subject_name)}</div>
    </div>
    <table class="candidate-info-box">
        <tr>
            <td>Candidate Name: ____________________________</td>
            <td>Roll / Seat No.: ____________________________</td>
        </tr>
        <tr>
            <td>Paper Set (A / B / C / D): __________________</td>
            <td>Invigilator Signature: ______________________</td>
        </tr>
    </table>
    <table class="match-pair-table">
        <thead>
            <tr>
                <th>Q. No.</th>
                <th>Candidate Response / OMR Bubbles</th>
                <th style="text-align: right;">Examiner Marks</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>
</div>
</body>
</html>
"""
