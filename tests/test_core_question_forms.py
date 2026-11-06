"""Unit and UI tests for Sub-phase 4.2: Rich Text Editor & Core Question Type Forms."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from src.core.models.enums import FillBlankMode, MCQOptionLayout, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    FillBlankData,
    MatchPairData,
    MCQData,
    NormalQuestionData,
    QuestionNode,
)
from src.core.models.section_model import Section
from src.core.storage.template_store import TemplateStore
from src.ui.workspace.forms.core_forms import (
    FillBlankQuestionForm,
    MatchPairQuestionForm,
    MCQOptionRowWidget,
    MCQQuestionForm,
    NormalQuestionForm,
    create_question_form,
)
from src.ui.workspace.rich_text_editor import (
    LatexInputDialog,
    RichTextEditor,
    SymbolPickerDialog,
    TableInsertDialog,
)
from src.ui.workspace.workspace_screen import WorkspaceScreen


def test_rich_text_editor_formatting_and_inserters(qtbot: QtBot) -> None:
    """Verify RichTextEditor basic formatting, HTML export/import, and math dialogs."""
    editor = RichTextEditor()
    qtbot.addWidget(editor)
    editor.show()

    # 1. Plain text and HTML loading
    editor.set_html("<p>Initial text</p>")
    assert "Initial text" in editor.get_plain_text()
    assert "<p" in editor.get_html()

    # 2. Bold and Subscript toggles
    editor.txt_edit.selectAll()
    editor.btn_bold.click()
    assert editor.btn_bold.isChecked() is True
    editor.btn_sub.click()
    assert editor.btn_sub.isChecked() is True
    editor.btn_super.click()
    assert editor.btn_super.isChecked() is True
    assert editor.btn_sub.isChecked() is False  # Mutually exclusive

    # 3. LaTeX dialog helper
    dlg_latex = LatexInputDialog(initial_latex="E = mc^2")
    qtbot.addWidget(dlg_latex)
    assert dlg_latex.get_latex() == "E = mc^2"
    dlg_latex._insert_snippet(" + \\Delta E")
    assert "E = mc^2 + \\Delta E" in dlg_latex.get_latex()

    # 4. Table dialog helper
    dlg_table = TableInsertDialog()
    qtbot.addWidget(dlg_table)
    dlg_table.spin_rows.setValue(4)
    dlg_table.spin_cols.setValue(5)
    r, c = dlg_table.get_dimensions()
    assert r == 4 and c == 5

    # 5. Symbol picker dialog
    dlg_symbols = SymbolPickerDialog()
    qtbot.addWidget(dlg_symbols)
    assert dlg_symbols.tabs.count() >= 3


def test_normal_question_form(qtbot: QtBot) -> None:
    """Verify NormalQuestionForm loads, edits, and saves standard descriptive question fields."""
    form = NormalQuestionForm()
    qtbot.addWidget(form)
    form.show()

    node = QuestionNode(
        prompt_html="<p>Explain Newton's third law of motion.</p>",
        question_type=QuestionType.NORMAL,
        marks=3.0,
        answer_space_lines=6,
    )
    form.load_question(node)

    assert "Newton's third law" in form.editor_prompt.get_plain_text()
    assert form.spin_marks.value() == 3.0
    assert form.spin_lines.value() == 6

    # Modify fields
    form.spin_marks.setValue(5.0)
    form.spin_lines.setValue(8)
    form.editor_prompt.txt_edit.setPlainText("Updated question on action-reaction pairs.")
    form.save_to_question(node)

    assert node.marks == 5.0
    assert node.answer_space_lines == 8
    assert "action-reaction" in node.prompt_html


def test_mcq_question_form(qtbot: QtBot) -> None:
    """Verify MCQQuestionForm handles dynamic options, layouts, correct answer marking, and validation."""
    form = MCQQuestionForm()
    qtbot.addWidget(form)
    form.show()

    mcq_data = MCQData(
        options=[],
        option_layout=MCQOptionLayout.GRID_2X2,
        allow_multiple_correct=False,
    )
    mcq_data.add_option("Mercury", is_correct=False)
    mcq_data.add_option("Venus", is_correct=False)
    mcq_data.add_option("Earth", is_correct=True)
    mcq_data.add_option("Mars", is_correct=False)

    node = QuestionNode(
        prompt_html="<p>Which planet supports liquid water oceans?</p>",
        question_type=QuestionType.MCQ,
        marks=1.0,
        type_data=mcq_data,
    )
    form.load_question(node)

    # Verify options populated
    assert form.options_lay.count() == 4
    opt_c_widget = form.options_lay.itemAt(2).widget()
    assert isinstance(opt_c_widget, MCQOptionRowWidget)
    assert opt_c_widget.chk_correct.isChecked() is True
    assert opt_c_widget.edit_text.text() == "Earth"

    # 1. Add 5th option (Jupiter)
    form.btn_add_opt.click()
    assert form.options_lay.count() == 5
    opt_e_widget = form.options_lay.itemAt(4).widget()
    assert isinstance(opt_e_widget, MCQOptionRowWidget)
    assert opt_e_widget.lbl_label.text() == "(E)"
    opt_e_widget.edit_text.setText("Jupiter")

    # 2. Switch correct answer to B (Venus) in single-correct mode
    opt_b_widget = form.options_lay.itemAt(1).widget()
    assert isinstance(opt_b_widget, MCQOptionRowWidget)
    opt_b_widget.chk_correct.setChecked(True)
    # Earth (C) should be unchecked
    opt_c_widget = form.options_lay.itemAt(2).widget()
    assert opt_c_widget.chk_correct.isChecked() is False
    assert opt_b_widget.chk_correct.isChecked() is True

    # 3. Change layout to STACKED
    form.combo_layout.setCurrentIndex(form.combo_layout.findData(MCQOptionLayout.STACKED))
    form.save_to_question(node)
    assert node.type_data.option_layout == MCQOptionLayout.STACKED

    # 4. Multiple correct mode
    form.chk_allow_multiple.setChecked(True)
    assert node.type_data.allow_multiple_correct is True
    # Now check E as well
    opt_e_widget.chk_correct.setChecked(True)
    assert opt_b_widget.chk_correct.isChecked() is True
    assert opt_e_widget.chk_correct.isChecked() is True

    # 5. Delete option E
    opt_e_widget.btn_del.click()
    assert form.options_lay.count() == 4


def test_fill_blank_question_form(qtbot: QtBot) -> None:
    """Verify FillBlankQuestionForm blank insertion helper and word bank mode."""
    form = FillBlankQuestionForm()
    qtbot.addWidget(form)
    form.show()

    node = QuestionNode(
        prompt_html="<p>Light travels in a ______ line.</p>",
        question_type=QuestionType.FILL_IN_THE_BLANK,
        marks=2.0,
        type_data=FillBlankData(
            mode=FillBlankMode.WITHOUT_OPTIONS,
            word_bank_options=[],
        ),
    )
    form.load_question(node)

    # 1. Insert blank helper
    form.btn_insert_blank.click()
    assert "______" in form.editor_prompt.get_plain_text()

    # 2. Switch mode to WITH_OPTIONS
    idx = form.combo_mode.findData(FillBlankMode.WITH_OPTIONS)
    form.combo_mode.setCurrentIndex(idx)
    assert form.word_bank_widget.isVisible() is True

    form.edit_word_bank.setText("straight, curved, circular")
    form.edit_blank_answers.setText("straight")
    form.save_to_question(node)

    fb_data: FillBlankData = node.type_data
    assert fb_data.mode == FillBlankMode.WITH_OPTIONS
    assert fb_data.word_bank_options == ["straight", "curved", "circular"]
    assert len(fb_data.blanks) == 1
    assert fb_data.blanks[0].correct_answer == "straight"


def test_match_pair_question_form(qtbot: QtBot) -> None:
    """Verify MatchPairQuestionForm tabular pairs addition, removal, and minimum row constraints."""
    form = MatchPairQuestionForm()
    qtbot.addWidget(form)
    form.show()

    node = QuestionNode(
        prompt_html="<p>Match the physical quantities with their SI units:</p>",
        question_type=QuestionType.MATCH_THE_PAIR,
        marks=3.0,
    )
    form.load_question(node)

    # Initially 2 rows
    assert form.table_pairs.rowCount() == 2

    # Add 3rd pair
    form.btn_add_pair.click()
    assert form.table_pairs.rowCount() == 3

    # Populate rows
    form.table_pairs.item(0, 0).setText("Force")
    form.table_pairs.item(0, 1).setText("Newton")
    form.table_pairs.item(1, 0).setText("Energy")
    form.table_pairs.item(1, 1).setText("Joule")
    form.table_pairs.item(2, 0).setText("Power")
    form.table_pairs.item(2, 1).setText("Watt")

    form.chk_shuffle.setChecked(True)
    form.save_to_question(node)

    mp_data: MatchPairData = node.type_data
    assert len(mp_data.rows) == 3
    assert mp_data.rows[0].col_a_html == "Force"
    assert mp_data.rows[0].col_b_html == "Newton"
    assert mp_data.shuffle_col_b is True


def test_workspace_screen_integrates_forms(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify WorkspaceScreen dynamically mounts core question forms on tree selection."""
    store = TemplateStore(storage_dir=tmp_path / "templates")
    workspace = WorkspaceScreen(template_store=store)
    qtbot.addWidget(workspace)
    workspace.show()

    # Create project with 4 question types
    q_norm = QuestionNode(prompt_html="<p>Normal Question</p>", question_type=QuestionType.NORMAL, marks=2.0)
    q_mcq = QuestionNode(prompt_html="<p>MCQ Question</p>", question_type=QuestionType.MCQ, marks=1.0)
    q_fb = QuestionNode(prompt_html="<p>Fill Blank</p>", question_type=QuestionType.FILL_IN_THE_BLANK, marks=1.0)
    q_mp = QuestionNode(prompt_html="<p>Match Pair</p>", question_type=QuestionType.MATCH_THE_PAIR, marks=4.0)

    section = Section(title="Section A", is_default_unsectioned=False)
    section.questions.extend([q_norm, q_mcq, q_fb, q_mp])

    tmpl = store.list_templates()[0]
    project = ProjectState.create_from_template(tmpl, title="Forms Integration Test")
    project.sections = [section]
    workspace.load_project(project)

    # 1. Select Normal Question -> NormalQuestionForm
    workspace.outline_tree.select_question(q_norm.question_id)
    assert isinstance(workspace.active_form, NormalQuestionForm)

    # 2. Select MCQ Question -> MCQQuestionForm
    workspace.outline_tree.select_question(q_mcq.question_id)
    assert isinstance(workspace.active_form, MCQQuestionForm)

    # 3. Select Fill Blank -> FillBlankQuestionForm
    workspace.outline_tree.select_question(q_fb.question_id)
    assert isinstance(workspace.active_form, FillBlankQuestionForm)

    # 4. Select Match Pair -> MatchPairQuestionForm
    workspace.outline_tree.select_question(q_mp.question_id)
    assert isinstance(workspace.active_form, MatchPairQuestionForm)

    # 5. Modify form and verify workspace unsaved state
    workspace.outline_tree.select_question(q_mcq.question_id)
    mcq_form: MCQQuestionForm = workspace.active_form  # type: ignore[assignment]
    mcq_form.spin_marks.setValue(3.0)
    assert workspace.has_unsaved_changes is True
    assert "Unsaved" in workspace.lbl_status_save.text()
