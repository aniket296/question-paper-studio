"""Multi-Set Question Paper Generator, Shuffler & Cross-Set Difference Matrix Engine.

Generates synchronized parallel examination sets (e.g. Set A, Set B, Set C, Set D) with:
1. Top-level question permutations within sections (preserving choice pairs & passage links).
2. MCQ option permutations with automated ground-truth relabeling and synchronized answer keys.
3. Match the Pair Column B permutations with updated ground truth mappings.
4. Parameterized Numerical Dynamic variations across sets.
5. Cross-Set Difference & Equivalence Matrix mapping question numbers and correct options.
6. Unified master cross-set comparison tables for exam invigilators and evaluators.
"""

from __future__ import annotations

import copy
import html
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import NumberingFSM, QuestionTreeEngine
from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    MCQData,
    MatchPairData,
    NumericalDynamicData,
    QuestionNode,
)
from src.core.models.section_model import ChoiceGroup, Section, SharedPassage
from src.rendering.docx_exporter import DOCXExporter
from src.rendering.pdf_exporter import PDFExporter
from src.rendering.supplementary_builder import AnswerKeyEntry, SupplementaryBuilder


@dataclass
class ShufflingOptions:
    """Configuration options for multi-set paper generation."""

    shuffle_questions: bool = True
    shuffle_mcq_options: bool = True
    shuffle_match_pairs: bool = True
    vary_numerical_seeds: bool = True
    keep_choice_groups_contiguous: bool = True
    preserve_set_a_order: bool = False
    master_seed: int = 42


@dataclass
class QuestionCrossSetMapping:
    """Row in the cross-set comparison matrix mapping a question across all sets."""

    question_id: str
    original_number: str
    marks: float
    prompt_snippet: str
    set_numbers: Dict[str, str] = field(default_factory=dict)
    set_answers: Dict[str, str] = field(default_factory=dict)


@dataclass
class MultiSetGenerationResult:
    """Complete bundle containing all generated sets and the cross-set mapping matrix."""

    sets: Dict[str, ProjectState]  # set_id (e.g. "Set A", "Set B") -> ProjectState
    mapping_matrix: List[QuestionCrossSetMapping]
    set_identifiers: List[str]     # e.g. ["A", "B", "C", "D"]
    master_seed: int


class MultiSetShuffler:
    """Engine orchestrating multi-set examination generation and cross-set answer key synchronization."""

    @staticmethod
    def _strip_tags(raw_html: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", raw_html or "")).strip()

    @staticmethod
    def generate_sets(
        base_project: ProjectState,
        set_identifiers: Optional[List[str]] = None,
        options: Optional[ShufflingOptions] = None,
    ) -> MultiSetGenerationResult:
        """Generate parallel question paper sets with synchronized answer keys."""
        opts = options or ShufflingOptions()
        set_ids = set_identifiers or ["A", "B", "C", "D"]
        if not set_ids:
            set_ids = ["A"]

        # Ensure base project numbering is up to date
        NumberingFSM.resolve_project(base_project)

        generated_sets: Dict[str, ProjectState] = {}

        for idx, s_id in enumerate(set_ids):
            is_first_set = (idx == 0)
            should_shuffle = not (is_first_set and opts.preserve_set_a_order)

            # Derive deterministic pseudo-random seed for this specific set
            set_seed = (opts.master_seed * 10007 + idx * 7919 + hash(s_id)) & 0x7FFFFFFF
            rng = random.Random(set_seed)

            # Clone base project (preserving question_ids so we can cross-reference across sets)
            cloned_proj = base_project.model_copy(deep=True)
            cloned_proj.exam_metadata.set_identifier = f"Set {s_id}" if not s_id.upper().startswith("SET") else s_id

            if should_shuffle:
                # 1. Shuffle top-level questions in each section
                if opts.shuffle_questions:
                    for sec in cloned_proj.sections:
                        MultiSetShuffler._shuffle_section_questions(
                            sec,
                            rng=rng,
                            keep_choice_contiguous=opts.keep_choice_groups_contiguous,
                        )

                # 2. Shuffle MCQ options, Match pairs, and vary numerical seeds
                all_questions = cloned_proj.all_questions_dfs()
                for q_idx, q in enumerate(all_questions):
                    if opts.shuffle_mcq_options and q.question_type == QuestionType.MCQ and isinstance(q.type_data, MCQData):
                        MultiSetShuffler._shuffle_mcq_options(q.type_data, rng=rng)

                    if opts.shuffle_match_pairs and q.question_type == QuestionType.MATCH_THE_PAIR and isinstance(q.type_data, MatchPairData):
                        MultiSetShuffler._shuffle_match_pair_column_b(q.type_data, rng=rng)

                    if opts.vary_numerical_seeds and q.question_type == QuestionType.NUMERICAL_DYNAMIC and isinstance(q.type_data, NumericalDynamicData):
                        MultiSetShuffler._instantiate_numerical_dynamic(q, seed=set_seed + q_idx * 31)

            # Re-resolve numbering for this set
            NumberingFSM.resolve_project(cloned_proj)
            generated_sets[s_id] = cloned_proj

        # 3. Build Cross-Set Difference Matrix
        matrix = MultiSetShuffler._build_cross_set_matrix(base_project, generated_sets, set_ids)

        return MultiSetGenerationResult(
            sets=generated_sets,
            mapping_matrix=matrix,
            set_identifiers=set_ids,
            master_seed=opts.master_seed,
        )

    # ========================================================================
    # Internal Shuffling Routines
    # ========================================================================

    @staticmethod
    def _shuffle_section_questions(
        section: Section,
        rng: random.Random,
        keep_choice_contiguous: bool = True,
    ) -> None:
        """Permute top-level questions in `section`, keeping choice pairs and shared passages grouped."""
        if len(section.questions) <= 1:
            return

        if not keep_choice_contiguous:
            rng.shuffle(section.questions)
            return

        # Cluster questions by choice_group_id or shared_passage_id
        clusters: List[List[QuestionNode]] = []
        visited_ids: Set[str] = set()

        for q in section.questions:
            if q.question_id in visited_ids:
                continue

            cluster = [q]
            visited_ids.add(q.question_id)

            # If part of choice group, gather all peers in this section
            if q.choice_group_id:
                for peer in section.questions:
                    if peer.question_id not in visited_ids and peer.choice_group_id == q.choice_group_id:
                        cluster.append(peer)
                        visited_ids.add(peer.question_id)

            # If linked to shared passage, gather all peers in this section
            elif q.shared_passage_id:
                for peer in section.questions:
                    if peer.question_id not in visited_ids and peer.shared_passage_id == q.shared_passage_id:
                        cluster.append(peer)
                        visited_ids.add(peer.question_id)

            clusters.append(cluster)

        # Shuffle the atomic clusters
        rng.shuffle(clusters)

        # Flatten back into section.questions
        flattened: List[QuestionNode] = []
        for c in clusters:
            flattened.extend(c)

        section.questions = flattened

    @staticmethod
    def _shuffle_mcq_options(data: MCQData, rng: random.Random) -> None:
        """Permute MCQ options while keeping `is_correct` synchronized and relabeling A, B, C, D."""
        if len(data.options) <= 1:
            return
        # Deep copy options list and shuffle
        shuffled = list(data.options)
        rng.shuffle(shuffled)
        data.options = shuffled
        data.relabel_options()

    @staticmethod
    def _shuffle_match_pair_column_b(data: MatchPairData, rng: random.Random) -> None:
        """Permute Column B indices for Match the Pair questions."""
        n = len(data.rows)
        if n <= 1:
            return
        # Generate a random permutation of 0..n-1
        perm = list(range(n))
        rng.shuffle(perm)
        for idx, row in enumerate(data.rows):
            row.shuffled_col_b_index = perm[idx]

    @staticmethod
    def _instantiate_numerical_dynamic(node: QuestionNode, seed: int) -> None:
        """Instantiate concrete numerical dynamic variable values for this specific set."""
        data: NumericalDynamicData = node.type_data  # type: ignore[assignment]
        if not data.variables or not data.formula_expr.strip():
            return
        res = DynamicNumericEngine.instantiate_question(node.prompt_html, data, seed=seed)
        node.prompt_html = res.instantiated_text
        data.instantiated_values = res.variables
        data.computed_answer = res.computed_answer

    # ========================================================================
    # Cross-Set Matrix Construction
    # ========================================================================

    @staticmethod
    def _build_cross_set_matrix(
        base_project: ProjectState,
        generated_sets: Dict[str, ProjectState],
        set_ids: List[str],
    ) -> List[QuestionCrossSetMapping]:
        """Build matrix mapping each question and its answer across all generated sets."""
        base_questions = base_project.all_questions_dfs()
        matrix: List[QuestionCrossSetMapping] = []

        # Pre-extract AnswerKeyEntry lookups for all sets
        set_keys: Dict[str, Dict[str, AnswerKeyEntry]] = {}
        for s_id, proj in generated_sets.items():
            entries = SupplementaryBuilder.extract_answer_key_entries(proj)
            set_keys[s_id] = {e.question_id: e for e in entries}

        for q in base_questions:
            clean_prompt = MultiSetShuffler._strip_tags(q.prompt_html)
            snippet = clean_prompt[:60] + ("..." if len(clean_prompt) > 60 else "")
            marks_val = MarksEngine.calculate_question_effective_marks(q).effective_marks

            mapping = QuestionCrossSetMapping(
                question_id=q.question_id,
                original_number=q.resolved_number or "•",
                marks=marks_val,
                prompt_snippet=snippet or f"[{q.question_type.value}]",
            )

            for s_id in set_ids:
                entries_map = set_keys.get(s_id, {})
                if q.question_id in entries_map:
                    entry = entries_map[q.question_id]
                    mapping.set_numbers[s_id] = entry.resolved_number
                    clean_ans = MultiSetShuffler._strip_tags(entry.concise_answer_html)
                    mapping.set_answers[s_id] = clean_ans or "—"
                else:
                    mapping.set_numbers[s_id] = "—"
                    mapping.set_answers[s_id] = "—"

            matrix.append(mapping)

        return matrix

    # ========================================================================
    # Master Comparison Sheet Document Generation
    # ========================================================================

    @staticmethod
    def generate_master_comparison_html(result: MultiSetGenerationResult) -> str:
        """Generate print-ready HTML5 master cross-set comparison table for evaluators."""
        set_cols_th = "".join(f"<th colspan='2'>Set {s_id}</th>" for s_id in result.set_identifiers)
        sub_cols_th = "".join("<th>Q#</th><th>Answer Key</th>" for _ in result.set_identifiers)

        rows_html: List[str] = []
        for row in result.mapping_matrix:
            set_cells = []
            for s_id in result.set_identifiers:
                q_num = html.escape(row.set_numbers.get(s_id, "—"))
                ans = html.escape(row.set_answers.get(s_id, "—"))
                set_cells.append(f"<td><b>{q_num}</b></td><td>{ans}</td>")
            cells_str = "".join(set_cells)
            rows_html.append(f"""
            <tr>
                <td><b>{html.escape(row.original_number)}</b></td>
                <td>{html.escape(row.prompt_snippet)}</td>
                <td>{row.marks:g} M</td>
                {cells_str}
            </tr>
            """)

        body_rows = "\n".join(rows_html)
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Master Cross-Set Equivalence & Answer Key Matrix</title>
    <style>
        body {{ font-family: 'Noto Sans', 'Segoe UI', Arial, sans-serif; padding: 24px; color: #0F172A; }}
        h1 {{ font-size: 18pt; margin-bottom: 4px; color: #1E293B; }}
        p.subtitle {{ color: #64748B; font-size: 10pt; margin-top: 0; margin-bottom: 16px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; }}
        th, td {{ border: 1px solid #CBD5E1; padding: 6px 10px; text-align: left; vertical-align: middle; }}
        th {{ background-color: #F1F5F9; font-weight: 700; color: #334155; }}
        tr:nth-child(even) {{ background-color: #F8FAFC; }}
    </style>
</head>
<body>
    <h1>Master Cross-Set Equivalence & Answer Key Matrix</h1>
    <p class="subtitle">Generated for Sets: {', '.join(result.set_identifiers)} | Master Seed: {result.master_seed}</p>
    <table>
        <thead>
            <tr>
                <th rowspan="2">Base Q#</th>
                <th rowspan="2">Question Summary</th>
                <th rowspan="2">Marks</th>
                {set_cols_th}
            </tr>
            <tr>
                {sub_cols_th}
            </tr>
        </thead>
        <tbody>
            {body_rows}
        </tbody>
    </table>
</body>
</html>"""

    @staticmethod
    def generate_master_comparison_docx(
        result: MultiSetGenerationResult,
        output_path: Path | str,
    ) -> Path:
        """Generate editable Microsoft Word (.docx) master comparison table."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".docx":
            dest = dest.with_suffix(".docx")
        dest.parent.mkdir(parents=True, exist_ok=True)

        doc = docx.Document()
        title_p = doc.add_paragraph()
        r = title_p.add_run("MASTER CROSS-SET EQUIVALENCE & ANSWER KEY MATRIX")
        r.bold = True
        r.font.size = Pt(14)
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        sub_p = doc.add_paragraph(f"Parallel Sets: {', '.join(result.set_identifiers)} | Master Seed: {result.master_seed}")
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        num_sets = len(result.set_identifiers)
        num_cols = 3 + (num_sets * 2)
        tbl = doc.add_table(rows=len(result.mapping_matrix) + 1, cols=num_cols)
        tbl.style = "Table Grid"

        # Headers
        headers = ["Base Q#", "Question Summary", "Marks"]
        for s_id in result.set_identifiers:
            headers.extend([f"Set {s_id} Q#", f"Set {s_id} Ans"])

        for idx, h_text in enumerate(headers):
            c = tbl.rows[0].cells[idx]
            c.text = h_text
            for run in c.paragraphs[0].runs:
                run.bold = True

        for r_idx, row in enumerate(result.mapping_matrix, start=1):
            r_cells = tbl.rows[r_idx].cells
            r_cells[0].text = row.original_number
            r_cells[1].text = row.prompt_snippet
            r_cells[2].text = f"{row.marks:g} M"

            col_offset = 3
            for s_id in result.set_identifiers:
                r_cells[col_offset].text = row.set_numbers.get(s_id, "—")
                r_cells[col_offset + 1].text = row.set_answers.get(s_id, "—")
                col_offset += 2

        doc.save(str(dest))
        return dest

    @staticmethod
    def export_all_sets(
        result: MultiSetGenerationResult,
        output_dir: Path | str,
        export_pdf: bool = True,
        export_docx: bool = True,
        export_answer_keys: bool = True,
        export_master_matrix: bool = True,
    ) -> List[Path]:
        """Batch export all parallel sets, answer keys, and master comparison document to `output_dir`."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        exported: List[Path] = []

        for s_id, proj in result.sets.items():
            base_filename = f"{proj.title.replace(' ', '_')}_Set_{s_id}"

            # 1. Question Paper PDF
            if export_pdf:
                pdf_path = out_path / f"{base_filename}.pdf"
                PDFExporter.export_project_to_pdf(proj, pdf_path, overwrite=True)
                exported.append(pdf_path)

            # 2. Question Paper DOCX
            if export_docx:
                docx_path = out_path / f"{base_filename}.docx"
                DOCXExporter.export_project_to_docx(proj, docx_path, overwrite=True)
                exported.append(docx_path)

            # 3. Synchronized Answer Keys
            if export_answer_keys:
                ak_pdf = out_path / f"{base_filename}_AnswerKey.pdf"
                PDFExporter.export_answer_key_pdf(proj, ak_pdf, overwrite=True)
                exported.append(ak_pdf)

                if export_docx:
                    ak_docx = out_path / f"{base_filename}_AnswerKey.docx"
                    DOCXExporter.export_answer_key_docx(proj, ak_docx, overwrite=True)
                    exported.append(ak_docx)

        # 4. Master Cross-Set Comparison Matrix
        if export_master_matrix:
            matrix_html = MultiSetShuffler.generate_master_comparison_html(result)
            html_path = out_path / "Master_Cross_Set_Equivalence_Matrix.html"
            html_path.write_text(matrix_html, encoding="utf-8")
            exported.append(html_path)

            if export_docx:
                matrix_docx = out_path / "Master_Cross_Set_Equivalence_Matrix.docx"
                MultiSetShuffler.generate_master_comparison_docx(result, matrix_docx)
                exported.append(matrix_docx)

        return exported
