"""Tests for Real-Time Live Preview Pane, Multi-Format Export Dialog & Workspace Integration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    FillBlankData,
    FillBlankMode,
    MCQData,
    MCQOption,
    MatchPairData,
    MatchPairRow,
    QuestionNode,
)
from src.core.models.template_model import Template
from src.core.storage.template_store import TemplateStore
from src.ui.workspace.export_dialog import ExportDialog
from src.ui.workspace.live_preview_pane import LivePreviewPane
from src.ui.workspace.workspace_screen import WorkspaceScreen


@pytest.fixture
def sample_project() -> ProjectState:
    """Fixture providing a test question paper project with sections and questions."""
    tmpl = Template(name="Preview Test Template")
    proj = ProjectState.create_from_template(tmpl, title="Physics Term Exam 2026")
    proj.exam_metadata.exam_name = "Final Physics Assessment"
    proj.exam_metadata.subject_name = "Physics"
    proj.exam_metadata.max_marks = 25.0

    sec = proj.sections[0]
    sec.title = "Section A: Multiple Choice Questions"

    q1 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Calculate the speed of light in vacuum: $c = \\frac{1}{\\sqrt{\\mu_0 \\varepsilon_0}}$.</p>",
        marks=5.0,
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="$3 \\times 10^8$ m/s", is_correct=True),
                MCQOption(label="B", text_html="$2 \\times 10^8$ m/s", is_correct=False),
                MCQOption(label="C", text_html="$3 \\times 10^6$ m/s", is_correct=False),
                MCQOption(label="D", text_html="$1.5 \\times 10^8$ m/s", is_correct=False),
            ],
            allow_multiple_correct=False,
        ),
    )
    sec.questions.append(q1)

    q2 = QuestionNode(
        question_type=QuestionType.MATCH_THE_PAIR,
        prompt_html="<p>Match the physical quantity with its dimensional formula:</p>",
        marks=4.0,
        type_data=MatchPairData(
            rows=[
                MatchPairRow(col_a_html="Force", col_b_html="[M L T^-2]", shuffled_col_b_index=0),
                MatchPairRow(col_a_html="Energy", col_b_html="[M L^2 T^-2]", shuffled_col_b_index=1),
            ],
        ),
    )
    sec.questions.append(q2)
    return proj


# ============================================================================
# LivePreviewPane Tests
# ============================================================================

def test_live_preview_pane_initialization_and_compilation(qapp: QApplication, sample_project: ProjectState) -> None:
    """Test preview pane loads HTML from project and emits signal."""
    pane = LivePreviewPane(project=sample_project)

    # Initial HTML should have been compiled
    html_content = pane.get_compiled_html()
    assert "<html" in html_content
    assert "Physics Term Exam 2026" in html_content
    assert "speed of light" in html_content

    # Check student mode by default
    assert not pane.teacher_preview_mode
    assert "Student View" in pane.btn_mode_toggle.text()

    # Toggle teacher preview mode
    updated_signals = []
    pane.preview_updated.connect(updated_signals.append)

    pane.set_teacher_preview_mode(True)
    assert pane.teacher_preview_mode
    assert "Teacher Preview" in pane.btn_mode_toggle.text()
    assert len(updated_signals) >= 1

    # Check that teacher preview output has key badge or solution
    teacher_html = pane.get_compiled_html()
    assert "teacher-preview" in teacher_html or "key-badge" in teacher_html or "correct-choice" in teacher_html


def test_live_preview_pane_zoom_controls(qapp: QApplication, sample_project: ProjectState) -> None:
    """Test zoom controls step correctly and clamp within limits."""
    pane = LivePreviewPane(project=sample_project)

    assert pane.zoom_factor == 1.0
    assert pane.lbl_zoom.text() == "100%"

    pane.zoom_in()
    assert pane.zoom_factor == 1.1
    assert pane.lbl_zoom.text() == "110%"

    pane.zoom_out()
    assert pane.zoom_factor == 1.0

    # Test reset
    pane.set_zoom_factor(1.8)
    assert pane.zoom_factor == 1.8
    pane.zoom_reset()
    assert pane.zoom_factor == 1.0

    # Test clamping limits
    pane.set_zoom_factor(0.1)  # Below min 0.4
    assert pane.zoom_factor == 0.4

    pane.set_zoom_factor(5.0)  # Above max 3.0
    assert pane.zoom_factor == 3.0


def test_live_preview_pane_debounced_refresh(qapp: QApplication, sample_project: ProjectState) -> None:
    """Test debounced background preview updates without locking."""
    pane = LivePreviewPane(project=sample_project)

    # Trigger debounced refresh
    pane.refresh_preview(immediate=False)
    assert pane.lbl_status.text() == "Compiling preview..."
    assert pane._debounce_timer.isActive()

    # Trigger immediate refresh
    pane.refresh_preview(immediate=True)
    assert not pane._debounce_timer.isActive()
    assert "Preview updated" in pane.lbl_status.text()


# ============================================================================
# ExportDialog Tests
# ============================================================================

def test_export_dialog_initialization(qapp: QApplication, sample_project: ProjectState, tmp_path: Path) -> None:
    """Test ExportDialog UI widgets initialize with correct defaults."""
    dlg = ExportDialog(sample_project, default_dir=tmp_path)

    assert dlg.chk_pdf.isChecked()
    assert dlg.chk_docx.isChecked()
    assert not dlg.chk_answer_key_pdf.isChecked()
    assert not dlg.chk_rubric_docx.isChecked()
    assert dlg.chk_overwrite.isChecked()
    assert dlg.txt_filename.text().startswith("Physics")


def test_export_dialog_validation_no_selection(qapp: QApplication, sample_project: ProjectState, tmp_path: Path) -> None:
    """Test that attempting export with 0 selected formats does nothing."""
    dlg = ExportDialog(sample_project, default_dir=tmp_path)
    dlg.chk_pdf.setChecked(False)
    dlg.chk_docx.setChecked(False)

    files = dlg.run_export()
    assert files == []


def test_export_dialog_batch_export_all_formats(qapp: QApplication, sample_project: ProjectState, tmp_path: Path) -> None:
    """Test batch export generating PDF, DOCX, Answer Key, Rubrics, and OMR files on disk."""
    dlg = ExportDialog(sample_project, default_dir=tmp_path)
    dlg.chk_open_folder.setChecked(False)  # Don't open explorer during test

    # Select all export options
    dlg.chk_pdf.setChecked(True)
    dlg.chk_docx.setChecked(True)
    dlg.chk_answer_key_pdf.setChecked(True)
    dlg.chk_answer_key_docx.setChecked(True)
    dlg.chk_rubric_pdf.setChecked(True)
    dlg.chk_rubric_docx.setChecked(True)
    dlg.chk_omr_pdf.setChecked(True)

    finished_payloads = []
    dlg.export_finished.connect(finished_payloads.append)

    generated = dlg.run_export()

    # Should have generated 7 distinct files
    assert len(generated) == 7
    assert len(finished_payloads) == 1
    assert len(finished_payloads[0]) == 7

    for fpath in generated:
        assert fpath.exists(), f"File {fpath} was not created on disk."
        assert fpath.stat().st_size > 0, f"File {fpath} is empty."


# ============================================================================
# Workspace Integration Tests
# ============================================================================

def test_workspace_screen_live_preview_and_export_integration(
    qapp: QApplication,
    sample_project: ProjectState,
    tmp_path: Path,
) -> None:
    """Test WorkspaceScreen right pane tabs, live preview syncing, and export dialog wiring."""
    ws = WorkspaceScreen()
    ws.load_project(sample_project)

    # Verify right pane tabs
    assert hasattr(ws, "right_tabs")
    assert ws.right_tabs.count() == 2
    assert "Live Preview" in ws.right_tabs.tabText(0)
    assert "Blueprint & Audit" in ws.right_tabs.tabText(1)

    # Verify live preview widget attached
    assert ws.live_preview is not None
    html_preview = ws.live_preview.get_compiled_html()
    assert "Physics Term Exam 2026" in html_preview

    # Verify export button triggers dialog
    assert ws.btn_export.isEnabled()
    assert ws.btn_print.isEnabled()

    # Switch tab to audit and back
    ws.right_tabs.setCurrentIndex(1)
    assert ws.right_tabs.currentIndex() == 1
    ws.right_tabs.setCurrentIndex(0)
    assert ws.right_tabs.currentIndex() == 0

    # Toggle preview visibility
    ws.btn_toggle_preview.setChecked(False)
    assert ws.right_preview_container.isHidden()
    ws.btn_toggle_preview.setChecked(True)
    assert not ws.right_preview_container.isHidden()
