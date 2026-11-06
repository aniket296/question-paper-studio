"""Unit and UI tests for Sub-phase 3.1: Application Theme, Home Hub & Template Management Screen."""

from __future__ import annotations

from pathlib import Path

import docx
from pytestqt.qtbot import QtBot

from src.core.models import ProjectState, QuestionNode
from src.core.storage import QPFArchive
from src.ui import MainWindow, ThemeManager
from src.ui.home import TemplateImportDialog


def test_theme_manager_font_registration_and_stylesheets() -> None:
    """Verify bundled Noto Sans / Devanagari fonts register and light/dark QSS stylesheets build cleanly."""
    families = ThemeManager.register_bundled_fonts()
    assert len(families) >= 1

    light_qss = ThemeManager.build_stylesheet(dark_mode=False)
    dark_qss = ThemeManager.build_stylesheet(dark_mode=True)
    assert "QMainWindow" in light_qss
    assert "#2563EB" in light_qss
    assert "#0F172A" in dark_qss


def test_home_screen_project_creation_gating_and_navigation(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify Create Question Paper requires selecting a template first, then routes to Workspace."""
    win = MainWindow(workspace_dir=tmp_path / "ws")
    qtbot.addWidget(win)
    win.show()

    home = win.home_screen
    # Initially no template is selected -> Create Question Paper button is disabled
    home.select_template_by_id(None)
    assert home.btn_create_paper.isEnabled() is False
    assert win.stack.currentIndex() == MainWindow.ROUTE_HOME

    # Select 'Standard School A4' template -> Create Question Paper button becomes enabled
    selected_ok = home.select_template_by_id("builtin-standard-school-a4")
    assert selected_ok is True
    assert home.btn_create_paper.isEnabled() is True

    # Trigger Create Question Paper -> routes to ROUTE_WORKSPACE with embedded template snapshot
    created = home.on_create_question_paper("Unit Test Physics Paper")
    assert created is True
    assert win.stack.currentIndex() == MainWindow.ROUTE_WORKSPACE
    assert win.active_project is not None
    assert win.active_project.title == "Unit Test Physics Paper"
    assert win.active_project.template_snapshot.name == "Standard School A4"

    # Navigate back to Home Screen
    win.navigate_home(force=True)
    assert win.stack.currentIndex() == MainWindow.ROUTE_HOME

    # Navigate to Create Template -> routes to ROUTE_TEMPLATE_EDITOR
    home.btn_create_template.click()
    assert win.stack.currentIndex() == MainWindow.ROUTE_TEMPLATE_EDITOR
    assert win.active_template_editing is not None


def test_template_duplication_renaming_deletion_and_saved_paper_immunity(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Verify template duplication, renaming, deletion on Home Screen, and immunity of saved `.qpf` papers."""
    win = MainWindow(workspace_dir=tmp_path / "ws")
    qtbot.addWidget(win)
    home = win.home_screen

    initial_count = home.template_list.count()
    assert initial_count >= 3

    # Select built-in template and duplicate it
    home.select_template_by_id("builtin-standard-school-a4")
    dup = home.on_duplicate_selected_template(new_name="Duplicated Academy Template")
    assert dup is not None
    assert home.template_list.count() == initial_count + 1

    # Rename the duplicated template
    renamed = home.on_rename_selected_template(new_name="Renamed Academy Template")
    assert renamed is not None
    assert renamed.name == "Renamed Academy Template"

    # Save a `.qpf` project in the workspace using this template
    paper = ProjectState.create_from_template(renamed, title="Saved Biology Exam")
    paper.sections[0].add_question(QuestionNode(prompt_html="<p>Define osmosis.</p>", marks=2.0))
    saved_qpf_path = win.autosave_manager.projects_dir / "biology_exam.qpf"
    QPFArchive.save_qpf(paper, saved_qpf_path, overwrite=True)
    home.refresh_recent_projects()
    assert home.project_list.count() == 1

    # Delete the template from the Home Screen
    deleted = home.on_delete_selected_template(confirm=True)
    assert deleted is True
    assert home.template_list.count() == initial_count

    # Open the saved `.qpf` paper from the Recent list and verify its template snapshot is intact
    home.project_list.setCurrentRow(0)
    opened_proj = home.on_open_selected_project()
    assert opened_proj is not None
    assert opened_proj.template_snapshot.name == "Renamed Academy Template"
    assert win.stack.currentIndex() == MainWindow.ROUTE_WORKSPACE

    # Return home, duplicate the saved `.qpf` project, and delete the duplicate
    win.navigate_home(force=True)
    home.project_list.setCurrentRow(0)
    dup_qpf = home.on_duplicate_selected_project()
    assert dup_qpf is not None and dup_qpf.exists()
    assert home.project_list.count() == 2

    home.project_list.setCurrentRow(0)
    del_proj_ok = home.on_delete_selected_project(confirm=True)
    assert del_proj_ok is True
    assert home.project_list.count() == 1


def test_template_import_dialog_and_startup_crash_recovery(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify `TemplateImportDialog` previews DOCX imports and `MainWindow` recovers crash snapshots."""
    win = MainWindow(workspace_dir=tmp_path / "ws")
    qtbot.addWidget(win)

    sample_docx = tmp_path / "college_template.docx"
    doc = docx.Document()
    doc.sections[0].header.paragraphs[0].text = "INDIAN INSTITUTE OF SCIENCE"
    doc.save(str(sample_docx))

    dlg = TemplateImportDialog(
        win.template_store,
        parent=win,
        initial_file_path=sample_docx,
    )
    qtbot.addWidget(dlg)
    assert dlg.imported_template is not None
    assert dlg.confirm_btn.isEnabled() is True
    assert "Editable Elements" in dlg.report_view.toPlainText()
    dlg._on_confirm_clicked()

    # Simulate an unrecovered autosave snapshot and test `check_and_prompt_crash_recovery`
    crash_paper = ProjectState(title="Recovered Unsaved Paper")
    win.autosave_manager.perform_autosave(crash_paper)

    recovered = win.check_and_prompt_crash_recovery(auto_accept=True)
    assert recovered is not None
    assert recovered.title == "Recovered Unsaved Paper"
    assert win.stack.currentIndex() == MainWindow.ROUTE_WORKSPACE
