"""Unit and UI tests for Sub-phase 4.1: 3-Pane Workspace Shell, Exam Info Bar & Outline Tree."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from src.core.engine.numbering_fsm import QuestionTreeEngine
from src.core.models.enums import QuestionType
from src.core.models.project_model import ExamMetadata, ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import Section
from src.core.models.template_model import Template
from src.core.storage.qpf_archive import QPFArchive
from src.core.storage.template_store import TemplateStore
from src.ui.main_window import MainWindow
from src.ui.workspace.exam_info_bar import ExamInfoBar
from src.ui.workspace.outline_tree import OutlineTreeWidget
from src.ui.workspace.workspace_screen import WorkspaceScreen


def test_exam_info_bar_editing_and_collapsing(qtbot: QtBot) -> None:
    """Verify ExamInfoBar populates metadata, toggles expansion, and saves changes back to project."""
    bar = ExamInfoBar()
    qtbot.addWidget(bar)
    bar.show()

    # Initial state is collapsed
    assert bar._is_expanded is False
    assert bar.drawer_widget.isVisible() is False

    project = ProjectState(
        title="Mid-Term Physics Exam",
        exam_metadata=ExamMetadata(
            subject_name="Physics",
            class_semester="Grade 12",
            duration_minutes=150,
            max_marks=70.0,
            subject_code="PHY-042",
            exam_date="12 Nov 2026",
            set_identifier="Set A",
            general_instructions="Read all questions carefully.",
        ),
    )

    bar.load_from_project(project)
    assert bar.edit_title.text() == "Mid-Term Physics Exam"
    assert bar.edit_subject.text() == "Physics"
    assert bar.edit_class.text() == "Grade 12"
    assert bar.spin_duration.value() == 150
    assert bar.spin_max_marks.value() == 70.0
    assert bar.edit_subject_code.text() == "PHY-042"
    assert bar.txt_instructions.toPlainText() == "Read all questions carefully."

    # Toggle expansion
    bar.btn_toggle_expand.click()
    assert bar._is_expanded is True
    assert bar.drawer_widget.isVisible() is True
    assert "Less Details" in bar.btn_toggle_expand.text()

    # Modify values and save back to project
    bar.edit_title.setText("Updated Annual Physics Exam")
    bar.spin_max_marks.setValue(80.0)
    bar.txt_instructions.setPlainText("1. All questions compulsory.\n2. Calculators allowed.")
    bar.save_to_project(project)

    assert project.title == "Updated Annual Physics Exam"
    assert project.exam_metadata.max_marks == 80.0
    assert "Calculators allowed" in project.exam_metadata.general_instructions


def test_outline_tree_hierarchy_mutations_and_numbering(qtbot: QtBot) -> None:
    """Verify OutlineTreeWidget renders hierarchy, marks badges, and executes tree mutations."""
    tree_widget = OutlineTreeWidget()
    qtbot.addWidget(tree_widget)
    tree_widget.show()

    # Create a project with 2 questions
    q1 = QuestionNode(
        prompt_html="<p>What is Newton's first law?</p>",
        question_type=QuestionType.NORMAL,
        marks=2.0,
    )
    q2 = QuestionNode(
        prompt_html="<p>Explain quantum entanglement with an example.</p>",
        question_type=QuestionType.LONG_ANSWER,
        marks=5.0,
    )
    section = Section(title="Section A: Core Theory", is_default_unsectioned=False)
    section.questions.extend([q1, q2])

    project = ProjectState(title="Physics Paper", sections=[section])
    tree_widget.load_project(project)

    # Verify tree root items (1 section item containing 2 questions)
    assert tree_widget.tree.topLevelItemCount() == 1
    sec_item = tree_widget.tree.topLevelItem(0)
    assert sec_item.childCount() == 2

    q1_item = sec_item.child(0)
    assert "Newton's" in q1_item.text(0)
    assert "[2 M]" in q1_item.text(1)
    assert "Normal" in q1_item.text(2)

    # 1. Add top-level question
    tree_widget.select_question(q1.question_id)
    tree_widget.on_add_question()
    assert len(section.questions) == 3

    # 2. Add child sub-question to Q1
    tree_widget.select_question(q1.question_id)
    tree_widget.on_add_sub_question()
    assert len(q1.children) == 1
    assert q1.children[0].marks == 1.0

    # 3. Duplicate question
    tree_widget.select_question(q1.question_id)
    tree_widget.on_duplicate()
    assert len(section.questions) == 4

    # 4. Move Down & Move Up
    tree_widget.select_question(q1.question_id)
    moved_down = QuestionTreeEngine.move_down(project, q1.question_id)
    assert moved_down is True
    tree_widget.load_project(project, select_question_id=q1.question_id)

    moved_up = QuestionTreeEngine.move_up(project, q1.question_id)
    assert moved_up is True

    # 5. Delete question
    cur_count = len(section.questions)
    # Select last question in section and delete it
    last_q = section.questions[-1]
    tree_widget.select_question(last_q.question_id)
    tree_widget.on_delete()
    assert len(section.questions) == cur_count - 1


def test_workspace_screen_full_workflow(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify WorkspaceScreen 3-pane layout, marks audit, undo/redo, template swap, and .qpf saving."""
    tmpl_store = TemplateStore(storage_dir=tmp_path / "templates")
    workspace = WorkspaceScreen(template_store=tmpl_store)
    qtbot.addWidget(workspace)
    workspace.show()

    # Create project with 1 section and 2 questions totaling 10 marks
    q1 = QuestionNode(
        prompt_html="<p>Define electric flux.</p>",
        question_type=QuestionType.SHORT_ANSWER,
        marks=4.0,
    )
    q2 = QuestionNode(
        prompt_html="<p>Derive Gauss's law from Coulomb's law.</p>",
        question_type=QuestionType.LONG_ANSWER,
        marks=6.0,
    )
    tmpl = tmpl_store.list_templates()[0]
    project = ProjectState.create_from_template(tmpl, title="Electrostatics Test")
    project.exam_metadata.max_marks = 10.0
    project.sections[0].questions.extend([q1, q2])

    workspace.load_project(project)

    # 1. Verify Status Bar & Summary Card (10 / 10 marks -> Balanced)
    assert "10 / 10" in workspace.lbl_status_marks.text()
    assert "Balanced" in workspace.lbl_status_balance.text()
    assert "Questions: 2" in workspace.lbl_status_qcount.text()

    # 2. Verify Outline Tree selection updates Center Pane preview
    workspace.outline_tree.select_question(q1.question_id)
    assert "Define electric flux" in workspace.lbl_editor_preview.text()
    assert "4 M" in workspace.lbl_active_meta.text()

    # 3. Test Undo / Redo on adding a question
    assert workspace.btn_undo.isEnabled() is False
    workspace.outline_tree.on_add_question()
    assert len(workspace.project.sections[0].questions) == 3
    assert workspace.btn_undo.isEnabled() is True

    # Undo addition
    workspace.undo()
    assert len(workspace.project.sections[0].questions) == 2
    assert workspace.btn_redo.isEnabled() is True

    # Redo addition
    workspace.redo()
    assert len(workspace.project.sections[0].questions) == 3

    # 4. Test Marks Discrepancy Detection: change Max Marks to 20
    workspace.info_bar.spin_max_marks.setValue(20.0)
    # Total is now 12 (4 + 6 + 2), max is 20 -> mismatch -8 M
    assert "Mismatch" in workspace.lbl_status_balance.text()

    # 5. Test Template Hot-Swapping
    assert len(tmpl_store.list_templates()) >= 2
    target_tmpl = tmpl_store.list_templates()[1]
    idx = workspace.combo_template.findData(target_tmpl.template_id)
    assert idx >= 0
    workspace.combo_template.setCurrentIndex(idx)
    assert workspace.project.template_snapshot.name == target_tmpl.name

    # 6. Test Saving to .qpf archive
    save_file = tmp_path / "electrostatics_final.qpf"
    saved_path = workspace.save_project(custom_path=save_file)
    assert saved_path.exists()
    assert saved_path.suffix == ".qpf"
    assert workspace.has_unsaved_changes is False

    # Verify saved .qpf can be unpacked and loaded accurately
    loaded_result = QPFArchive.load_qpf(saved_path)
    loaded_project = loaded_result.project
    assert loaded_project.title == "Electrostatics Test"
    assert len(loaded_project.sections[0].questions) == 3
    assert loaded_project.template_snapshot.name == target_tmpl.name


def test_main_window_workspace_routing_and_navigation(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify MainWindow seamlessly routes to WorkspaceScreen and handles Back to Home navigation."""
    win = MainWindow(workspace_dir=tmp_path / "ws")
    qtbot.addWidget(win)
    win.show()

    # Route 0: Home Screen initially
    assert win.stack.currentIndex() == MainWindow.ROUTE_HOME

    # Select template and trigger Create Question Paper
    win.home_screen.select_template_by_id("builtin-standard-school-a4")
    created = win.home_screen.on_create_question_paper("Chemistry Board Exam 2026")
    assert created is True

    # Stack switched to ROUTE_WORKSPACE with active WorkspaceScreen
    assert win.stack.currentIndex() == MainWindow.ROUTE_WORKSPACE
    assert isinstance(win.workspace_view, WorkspaceScreen)
    assert win.workspace_view.project is not None
    assert win.workspace_view.project.title == "Chemistry Board Exam 2026"

    # Navigate back to Home Screen
    win.navigate_home(force=True)
    assert win.stack.currentIndex() == MainWindow.ROUTE_HOME
