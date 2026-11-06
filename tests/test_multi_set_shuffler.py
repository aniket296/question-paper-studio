"""Tests for Multi-Set Question Paper Generator, Shuffler & Cross-Set Difference Matrix UI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.core.engine.multi_set_shuffler import (
    MultiSetGenerationResult,
    MultiSetShuffler,
    QuestionCrossSetMapping,
    ShufflingOptions,
)
from src.core.models.enums import ChoiceRuleType, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    MatchPairData,
    MatchPairRow,
    MCQData,
    MCQOption,
    NumericalDynamicData,
    NumericVariableRange,
    QuestionNode,
)
from src.core.models.section_model import ChoiceGroup
from src.core.models.template_model import Template
from src.ui.advanced.multi_set_dialog import MultiSetDialog
from src.ui.workspace.workspace_screen import WorkspaceScreen


@pytest.fixture
def exam_project() -> ProjectState:
    tmpl = Template(name="Shuffler Test Template")
    proj = ProjectState.create_from_template(tmpl, title="Advanced Physics Exam")
    sec = proj.sections[0]
    sec.title = "Section A: Theory & Concepts"

    # MCQ 1
    q1 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>What is the SI unit of electric current?</p>",
        marks=2.0,
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="Ampere", is_correct=True),
                MCQOption(label="B", text_html="Volt", is_correct=False),
                MCQOption(label="C", text_html="Ohm", is_correct=False),
                MCQOption(label="D", text_html="Watt", is_correct=False),
            ],
            allow_multiple_correct=False,
        ),
    )
    sec.questions.append(q1)

    # MCQ 2
    q2 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Which particle has a negative charge?</p>",
        marks=2.0,
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="Proton", is_correct=False),
                MCQOption(label="B", text_html="Electron", is_correct=True),
                MCQOption(label="C", text_html="Neutron", is_correct=False),
                MCQOption(label="D", text_html="Positron", is_correct=False),
            ],
            allow_multiple_correct=False,
        ),
    )
    sec.questions.append(q2)

    # Match the Pair Question
    q3 = QuestionNode(
        question_type=QuestionType.MATCH_THE_PAIR,
        prompt_html="<p>Match the physical laws with their discoverers:</p>",
        marks=3.0,
        type_data=MatchPairData(
            rows=[
                MatchPairRow(col_a_html="Universal Gravitation", col_b_html="Newton", shuffled_col_b_index=0),
                MatchPairRow(col_a_html="Electromagnetic Induction", col_b_html="Faraday", shuffled_col_b_index=1),
                MatchPairRow(col_a_html="General Relativity", col_b_html="Einstein", shuffled_col_b_index=2),
            ],
        ),
    )
    sec.questions.append(q3)

    # Dynamic Numerical Question
    q4 = QuestionNode(
        question_type=QuestionType.NUMERICAL_DYNAMIC,
        prompt_html="<p>Calculate momentum: $p = m \\times v$ for mass {{m}} kg and velocity {{v}} m/s.</p>",
        marks=3.0,
        type_data=NumericalDynamicData(
            formula_expr="m * v",
            unit="kg·m/s",
            variables={
                "m": NumericVariableRange(min_val=2.0, max_val=10.0, precision=0),
                "v": NumericVariableRange(min_val=5.0, max_val=25.0, precision=0),
            },
        ),
    )
    sec.questions.append(q4)

    # OR Choice Pair questions (q5 and q6)
    q5 = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Option A: State the First Law of Thermodynamics.</p>",
        marks=5.0,
    )
    q6 = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Option B: State Carnot's Theorem for heat engines.</p>",
        marks=5.0,
    )
    grp = ChoiceGroup(
        rule_type=ChoiceRuleType.OR_PAIR,
        question_ids=[q5.question_id, q6.question_id],
    )
    q5.choice_group_id = grp.choice_group_id
    q6.choice_group_id = grp.choice_group_id
    sec.choice_groups.append(grp)
    sec.questions.extend([q5, q6])

    return proj


# ============================================================================
# Core Shuffler Tests
# ============================================================================

def test_deterministic_multi_set_generation(exam_project: ProjectState) -> None:
    """Test that multi-set generation with the same master seed produces identical sets."""
    opts = ShufflingOptions(master_seed=12345)
    res1 = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C"], options=opts)
    res2 = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C"], options=opts)

    assert set(res1.sets.keys()) == {"A", "B", "C"}
    assert set(res2.sets.keys()) == {"A", "B", "C"}

    # Compare Set B question sequence across the two runs
    set_b_qids_1 = [q.question_id for q in res1.sets["B"].sections[0].questions]
    set_b_qids_2 = [q.question_id for q in res2.sets["B"].sections[0].questions]
    assert set_b_qids_1 == set_b_qids_2


def test_mcq_option_shuffling_and_answer_key_synchronization(exam_project: ProjectState) -> None:
    """Test that MCQ option shuffling keeps the ground truth answer text 100% synchronized."""
    opts = ShufflingOptions(
        shuffle_questions=True,
        shuffle_mcq_options=True,
        master_seed=999,
    )
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C", "D"], options=opts)

    # Check MCQ 1: "What is the SI unit of electric current?" -> Correct answer must always be "Ampere"
    q1_id = exam_project.sections[0].questions[0].question_id

    for s_id, proj in result.sets.items():
        q_node = next(q for q in proj.all_questions_dfs() if q.question_id == q1_id)
        assert isinstance(q_node.type_data, MCQData)

        # Options must be relabeled A, B, C, D
        labels = [opt.label for opt in q_node.type_data.options]
        assert labels == ["A", "B", "C", "D"]

        # Exactly 1 option must be marked is_correct
        correct_opts = [opt for opt in q_node.type_data.options if opt.is_correct]
        assert len(correct_opts) == 1
        assert correct_opts[0].text_html == "Ampere"


def test_match_the_pair_column_b_shuffling(exam_project: ProjectState) -> None:
    """Test that Match the Pair Column B permutations maintain ground truth mapping."""
    opts = ShufflingOptions(shuffle_match_pairs=True, master_seed=555)
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B"], options=opts)

    q3_id = exam_project.sections[0].questions[2].question_id
    for s_id, proj in result.sets.items():
        q_node = next(q for q in proj.all_questions_dfs() if q.question_id == q3_id)
        assert isinstance(q_node.type_data, MatchPairData)
        gt = q_node.type_data.ground_truth_mapping()
        # All 3 rows must be mapped
        assert set(gt.keys()) == {1, 2, 3}
        assert set(gt.values()).issubset({1, 2, 3})


def test_choice_groups_contiguous_clustering(exam_project: ProjectState) -> None:
    """Test that questions belonging to the same OR choice pair remain contiguous after shuffling."""
    opts = ShufflingOptions(
        shuffle_questions=True,
        keep_choice_groups_contiguous=True,
        master_seed=777,
    )
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C", "D"], options=opts)

    q5_id = exam_project.sections[0].questions[4].question_id
    q6_id = exam_project.sections[0].questions[5].question_id

    for s_id, proj in result.sets.items():
        sec_qids = [q.question_id for q in proj.sections[0].questions]
        idx5 = sec_qids.index(q5_id)
        idx6 = sec_qids.index(q6_id)
        # Difference in indices must be exactly 1 (adjacent)
        assert abs(idx5 - idx6) == 1, f"Choice pair separated in Set {s_id}: idx5={idx5}, idx6={idx6}"


def test_cross_set_difference_matrix_construction(exam_project: ProjectState) -> None:
    """Test Cross-Set Difference Matrix structure and row mapping."""
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C", "D"])
    matrix = result.mapping_matrix

    assert len(matrix) == len(exam_project.all_questions_dfs())
    for row in matrix:
        assert isinstance(row, QuestionCrossSetMapping)
        assert row.original_number != ""
        assert row.marks > 0
        assert set(row.set_numbers.keys()) == {"A", "B", "C", "D"}
        assert set(row.set_answers.keys()) == {"A", "B", "C", "D"}


def test_master_comparison_documents_generation(exam_project: ProjectState, tmp_path: Path) -> None:
    """Test master equivalence table generation in HTML5 and Microsoft Word DOCX formats."""
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B", "C"])

    # HTML
    html_doc = MultiSetShuffler.generate_master_comparison_html(result)
    assert "<html" in html_doc
    assert "Set A" in html_doc and "Set B" in html_doc and "Set C" in html_doc

    # DOCX
    docx_out = tmp_path / "Master_Equivalence_Matrix.docx"
    saved_path = MultiSetShuffler.generate_master_comparison_docx(result, docx_out)
    assert saved_path.exists()
    assert saved_path.stat().st_size > 0


def test_batch_export_all_sets(exam_project: ProjectState, tmp_path: Path) -> None:
    """Test batch exporting all sets, answer keys, and master comparison sheets to disk."""
    result = MultiSetShuffler.generate_sets(exam_project, set_identifiers=["A", "B"])

    exported = MultiSetShuffler.export_all_sets(
        result=result,
        output_dir=tmp_path,
        export_pdf=True,
        export_docx=True,
        export_answer_keys=True,
        export_master_matrix=True,
    )

    # 2 sets * (PDF + DOCX + AK_PDF + AK_DOCX) = 8 + Master HTML + Master DOCX = 10 files
    assert len(exported) >= 10
    for f in exported:
        assert f.exists(), f"File {f.name} does not exist"
        assert f.stat().st_size > 0, f"File {f.name} is empty"


# ============================================================================
# UI Dialog & Workspace Integration Tests
# ============================================================================

def test_multi_set_dialog_workflow(qapp: QApplication, exam_project: ProjectState, tmp_path: Path) -> None:
    """Test MultiSetDialog UI initialization, preview generation, and batch export."""
    dlg = MultiSetDialog(exam_project, default_export_dir=tmp_path)
    dlg.chk_open_folder.setChecked(False)

    assert dlg.generation_result is not None
    assert len(dlg.generation_result.sets) == 4  # Default A, B, C, D

    # Verify UI tables populated
    assert dlg.table_mapping.rowCount() > 0
    assert dlg.table_answers.rowCount() > 0
    assert dlg.table_set_stats.rowCount() == 4

    # Switch to 2 sets ("A, B") and regenerate
    dlg.txt_set_ids.setText("A, B")
    dlg._generate_sets_preview()
    assert len(dlg.generation_result.sets) == 2
    assert dlg.table_set_stats.rowCount() == 2

    # Run export
    files = dlg.run_export_all()
    assert len(files) >= 6
    for f in files:
        assert f.exists()


def test_workspace_screen_integrates_multi_set_dialog(qapp: QApplication, exam_project: ProjectState) -> None:
    """Test that WorkspaceScreen toolbar houses the Multi-Set button and triggers the dialog."""
    ws = WorkspaceScreen()
    ws.load_project(exam_project)

    assert hasattr(ws, "btn_multi_set")
    assert ws.btn_multi_set.isEnabled()
    assert "Multi-Set" in ws.btn_multi_set.text()

    # Open dialog headlessly
    dlg = ws.open_multi_set_dialog()
    assert dlg is not None
    assert isinstance(dlg, MultiSetDialog)
