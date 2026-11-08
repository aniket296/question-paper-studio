"""Automated tests for Sub-Phase 5.3: Advanced Modules (Question Bank Drawer, Blueprint Presets, Quality Audit Panel & Post-Exam Diagnostics)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtWidgets import QApplication

from src.core.models.enums import BloomLevel, DifficultyLevel, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    MarkingScheme,
    MCQData,
    MCQOption,
    QuestionNode,
    TaxonomyMetadata,
)
from src.core.models.template_model import Template
from src.core.storage.sqlite_bank import SQLiteQuestionBank
from src.ui.advanced import (
    BlueprintDialog,
    PostExamDialog,
    QualityCheckPanel,
    QuestionBankDrawer,
    RevisionHistoryDialog,
    get_built_in_pattern_presets,
)
from src.ui.workspace.workspace_screen import WorkspaceScreen


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_project() -> ProjectState:
    tmpl = Template(name="Advanced Modules Template")
    proj = ProjectState.create_from_template(tmpl, title="Semester Physics Exam")
    proj.exam_metadata.subject_name = "Physics"
    proj.exam_metadata.max_marks = 10.0

    sec = proj.sections[0]
    sec.title = "Section A"

    q1 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Calculate the kinetic energy of a 2 kg mass moving at 3 m/s.</p>",
        marks=2.0,
        taxonomy_metadata=TaxonomyMetadata(
            difficulty=DifficultyLevel.EASY,
            bloom_level=BloomLevel.APPLY,
            unit="Mechanics",
            topic="Energy",
        ),
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="9 J", is_correct=True),
                MCQOption(label="B", text_html="6 J", is_correct=False),
                MCQOption(label="C", text_html="18 J", is_correct=False),
                MCQOption(label="D", text_html="3 J", is_correct=False),
            ]
        ),
        marking_scheme=MarkingScheme(model_answer_html="<p>KE = 0.5 * 2 * 3^2 = 9 J</p>"),
    )

    q2 = QuestionNode(
        question_type=QuestionType.SHORT_ANSWER,
        prompt_html="<p>State Faraday's Law of Electromagnetic Induction.</p>",
        marks=3.0,
        taxonomy_metadata=TaxonomyMetadata(
            difficulty=DifficultyLevel.MODERATE,
            bloom_level=BloomLevel.UNDERSTAND,
            unit="Electromagnetism",
            topic="Induction",
        ),
    )

    q3 = QuestionNode(
        question_type=QuestionType.LONG_ANSWER,
        prompt_html="<p>Derive the wave equation for electromagnetic waves in vacuum from Maxwell's equations.</p>",
        marks=5.0,
        taxonomy_metadata=TaxonomyMetadata(
            difficulty=DifficultyLevel.DIFFICULT,
            bloom_level=BloomLevel.ANALYZE,
            unit="Electrodynamics",
            topic="Maxwell Equations",
        ),
    )

    sec.questions.extend([q1, q2, q3])
    return proj


def test_question_bank_drawer_search_insert_save_and_revisions(
    qtbot: QtBot,
    sample_project: ProjectState,
    tmp_path: Path,
) -> None:
    """Verify QuestionBankDrawer FTS5 search, filters, insertion into paper, saving active question, and revision history."""
    db_path = tmp_path / "test_bank.db"
    bank = SQLiteQuestionBank(db_path)

    try:
        # 1. Pre-populate bank with two questions
        q_bank_1 = sample_project.sections[0].questions[0].clone_with_new_ids()
        id1 = bank.add_question(q_bank_1)
        rec1 = bank.get_record(id1)
        assert rec1 is not None

        q_bank_2 = sample_project.sections[0].questions[1].clone_with_new_ids()
        id2 = bank.add_question(q_bank_2)
        rec2 = bank.get_record(id2)
        assert rec2 is not None

        # Update rec1 to create version 2
        q_bank_1_v2 = q_bank_1.model_copy(deep=True)
        q_bank_1_v2.prompt_html = "<p>Calculate the kinetic energy of a 4 kg mass moving at 5 m/s.</p>"
        bank.update_question(rec1.bank_item_id, q_bank_1_v2, change_note="Updated mass and velocity")

        # 2. Initialize WorkspaceScreen with bank and project
        ws = WorkspaceScreen(question_bank=bank)
        qtbot.addWidget(ws)
        ws.load_project(sample_project)
        initial_q_count = len(ws.project.sections[0].questions)
        assert initial_q_count == 3

        # Select first question in workspace so active_question is populated
        first_q_id = ws.project.sections[0].questions[2].question_id
        ws.outline_tree.select_question(first_q_id)

        # 3. Open QuestionBankDrawer via WorkspaceScreen
        drawer = ws.open_question_bank_drawer()
        qtbot.addWidget(drawer)
        assert isinstance(drawer, QuestionBankDrawer)
        assert drawer.table_results.rowCount() == 2

        # 4. Test FTS5 keyword search
        drawer.txt_query.setText("Faraday")
        drawer._on_search()
        assert drawer.table_results.rowCount() == 1
        assert drawer.selected_record is not None
        assert drawer.selected_record.bank_item_id == rec2.bank_item_id

        # Reset filters
        drawer._reset_filters()
        assert drawer.table_results.rowCount() == 2

        # Filter by QuestionType.MCQ
        mcq_idx = drawer.combo_type.findData(QuestionType.MCQ)
        drawer.combo_type.setCurrentIndex(mcq_idx)
        assert drawer.table_results.rowCount() == 1
        assert drawer.selected_record.bank_item_id == rec1.bank_item_id

        # 5. Test RevisionHistoryDialog & restoring v1
        rev_dlg = drawer._on_view_revisions()
        qtbot.addWidget(rev_dlg)
        assert isinstance(rev_dlg, RevisionHistoryDialog)
        assert rev_dlg.table_revs.rowCount() >= 2
        rev_dlg._on_restore(1)

        # Verify restored prompt
        restored_rec = bank.get_record(rec1.bank_item_id)
        assert restored_rec is not None
        assert "2 kg mass" in restored_rec.plain_text

        # 6. Test inserting selected question into active paper
        drawer.table_results.selectRow(0)
        drawer._on_insert_into_paper()
        assert len(ws.project.sections[0].questions) == initial_q_count + 1

        # Usage count in bank should have incremented
        updated_rec = bank.get_record(rec1.bank_item_id)
        assert updated_rec is not None
        assert updated_rec.usage_count == 1

        # 7. Test saving active question from paper into bank
        saved_rec = drawer._on_save_active_question()
        assert saved_rec is not None
        assert "Maxwell" in saved_rec.plain_text
    finally:
        bank.close()


def test_blueprint_dialog_presets_and_compliance_audit(
    qtbot: QtBot,
    sample_project: ProjectState,
) -> None:
    """Verify BlueprintDialog presets, target distribution editing, and compliance validation."""
    presets = get_built_in_pattern_presets()
    assert len(presets) >= 4
    preset_ids = {p.preset_id for p in presets}
    assert {"cbse_science_80", "jee_main_100", "univ_semester_50", "unit_quiz_25"}.issubset(preset_ids)

    ws = WorkspaceScreen()
    qtbot.addWidget(ws)
    ws.load_project(sample_project)

    dlg = ws.open_blueprint_dialog()
    qtbot.addWidget(dlg)
    assert isinstance(dlg, BlueprintDialog)
    assert dlg.active_blueprint is not None

    # Test modifying target marks and distributions
    dlg.spin_total_target.setValue(10.0)
    # Set Easy=2, Medium=3, Hard=5 to match sample_project exactly
    dlg.table_diff.item(0, 1).setText("2")
    dlg.table_diff.item(1, 1).setText("3")
    dlg.table_diff.item(2, 1).setText("5")

    # Set Bloom: Remember=0, Understand=3, Apply=2, Analyze=5, Evaluate=0, Create=0
    bloom_map = {
        "remember": "0",
        "understand": "3",
        "apply": "2",
        "analyze": "5",
        "evaluate": "0",
        "create": "0",
    }
    for r in range(dlg.table_bloom.rowCount()):
        lbl = dlg.table_bloom.item(r, 0).text().lower()
        dlg.table_bloom.item(r, 1).setText(bloom_map.get(lbl, "0"))

    dlg._on_target_changed()
    dlg._run_compliance_audit()
    assert "100% Compliant" in dlg.lbl_audit_status.text()

    # Test applying a built-in pattern preset (Unit Quiz 25 Marks)
    unit_idx = -1
    for i in range(dlg.combo_presets.count()):
        p = dlg.combo_presets.itemData(i)
        if p and p.preset_id == "unit_quiz_25":
            unit_idx = i
            break
    assert unit_idx >= 0
    dlg.combo_presets.setCurrentIndex(unit_idx)
    dlg._on_apply_preset()

    assert ws.project.exam_metadata.max_marks == 25.0
    assert len(ws.project.sections) == 3
    assert len(ws.project.all_questions_dfs()) == 12


def test_quality_check_panel_audit_and_navigation(
    qtbot: QtBot,
    sample_project: ProjectState,
) -> None:
    """Verify QualityCheckPanel heuristic defect detection, health score, and jump-to-question navigation."""
    # Introduce a defect: MCQ without any correct option marked
    bad_mcq = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Which particle has zero rest mass?</p>",
        marks=2.0,
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="Photon", is_correct=False),
                MCQOption(label="B", text_html="Electron", is_correct=False),
                MCQOption(label="C", text_html="Proton", is_correct=False),
                MCQOption(label="D", text_html="Neutron", is_correct=False),
            ]
        ),
    )
    sample_project.sections[0].questions.append(bad_mcq)

    ws = WorkspaceScreen()
    qtbot.addWidget(ws)
    ws.load_project(sample_project)

    panel = ws.open_quality_check_panel()
    qtbot.addWidget(panel)
    assert isinstance(panel, QualityCheckPanel)
    assert panel.audit_report is not None
    assert panel.audit_report.critical_count >= 1
    assert panel.table_issues.rowCount() >= 1

    # Select the critical issue row for bad_mcq and trigger jump
    target_row = 0
    for idx, issue in enumerate(panel.audit_report.issues):
        if issue.question_id == bad_mcq.question_id:
            target_row = idx
            break

    panel.table_issues.selectRow(target_row)
    panel._on_jump_to_question()

    assert ws.outline_tree.get_selected_question_id() == bad_mcq.question_id


def test_post_exam_dialog_psychometrics_and_exports(
    qtbot: QtBot,
    sample_project: ProjectState,
    tmp_path: Path,
) -> None:
    """Verify PostExamDialog candidate grid, P-value & D-value calculations, and CSV/HTML exports."""
    ws = WorkspaceScreen()
    qtbot.addWidget(ws)
    ws.load_project(sample_project)

    dlg = ws.open_post_exam_dialog()
    qtbot.addWidget(dlg)
    assert isinstance(dlg, PostExamDialog)
    assert len(dlg.questions) == 3
    assert dlg.table_marks.rowCount() == 15

    # Add a candidate row
    dlg._add_candidate_row()
    assert dlg.table_marks.rowCount() == 16

    # Simulate randomized 25-candidate class scores
    dlg._populate_initial_candidates(count=25, randomize=True)
    assert dlg.table_marks.rowCount() == 25
    assert dlg.table_metrics.rowCount() == 3
    assert len(dlg.item_metrics) == 3

    for metric in dlg.item_metrics:
        assert 0.0 <= float(metric["p_val"]) <= 1.0
        assert -1.0 <= float(metric["d_val"]) <= 1.0
        assert metric["rating"] in {
            "Excellent Item",
            "Good Item",
            "Marginal — Needs Review",
            "Poor Discrimination",
        }

    assert "Mean Score:" in dlg.lbl_stats_mean.text()
    assert "Standard Deviation:" in dlg.lbl_stats_sd.text()
    assert "Pass Rate" in dlg.lbl_stats_pass.text()

    # Export CSV and verify contents
    csv_path = tmp_path / "diagnostics.csv"
    exported_csv = dlg.export_csv(dest_path=csv_path)
    assert exported_csv == csv_path
    assert csv_path.exists()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "CANDIDATE SCORES" in csv_text
    assert "ITEM PSYCHOMETRICS" in csv_text
    assert "Student 01" in csv_text

    # Export HTML and verify contents
    html_path = tmp_path / "diagnostics.html"
    exported_html = dlg.export_html(dest_path=html_path)
    assert exported_html == html_path
    assert html_path.exists()
    html_text = html_path.read_text(encoding="utf-8")
    assert "Post-Exam Psychometric Diagnostic Report" in html_text
    assert "Difficulty (P)" in html_text
    assert "Discrimination (D)" in html_text
