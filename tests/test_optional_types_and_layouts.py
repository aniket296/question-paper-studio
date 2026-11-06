"""Tests for the 9 Optional Question Type Forms, Bilingual Prompts, Choice Groups & Shared Passages."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.core.models.enums import ChoiceRuleType, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    AssertionReasonData,
    CaseBasedData,
    DiagramLabelHotspot,
    DiagramLabellingData,
    FillBlankData,
    LongAnswerData,
    MatchPairData,
    MCQData,
    NormalQuestionData,
    NumericalDynamicData,
    NumericVariableRange,
    OrderingItem,
    OrderingSequencingData,
    QuestionNode,
    ShortAnswerData,
    SourceBasedData,
    TrueFalseData,
)
from src.core.models.section_model import ChoiceGroup, Section, SharedPassage
from src.core.models.template_model import Template
from src.ui.workspace.choice_passage_dialog import ChoiceGroupManagerDialog, SharedPassageDialog
from src.ui.workspace.forms.core_forms import (
    FillBlankQuestionForm,
    MatchPairQuestionForm,
    MCQQuestionForm,
    NormalQuestionForm,
    create_question_form,
)
from src.ui.workspace.forms.optional_forms import (
    AssertionReasonQuestionForm,
    CaseBasedQuestionForm,
    DiagramLabellingQuestionForm,
    LongAnswerQuestionForm,
    NumericalDynamicQuestionForm,
    OrderingSequencingQuestionForm,
    ShortAnswerQuestionForm,
    SourceBasedQuestionForm,
    TrueFalseQuestionForm,
)


@pytest.fixture
def test_project() -> ProjectState:
    tmpl = Template(name="Prog Disclosure Template")
    proj = ProjectState.create_from_template(tmpl, title="Comprehensive Exam 2026")
    sec = proj.sections[0]
    sec.title = "Section A"
    for i in range(4):
        q = QuestionNode(
            question_type=QuestionType.NORMAL,
            prompt_html=f"<p>Question statement {i + 1}</p>",
            marks=2.0,
        )
        sec.questions.append(q)
    return proj


# ============================================================================
# Form Factory Tests (All 13 Question Types)
# ============================================================================

def test_create_question_form_dispatches_all_13_types(qapp: QApplication) -> None:
    """Verify that create_question_form creates the exact specialized form for each QuestionType."""
    type_to_cls = {
        QuestionType.NORMAL: NormalQuestionForm,
        QuestionType.MCQ: MCQQuestionForm,
        QuestionType.FILL_IN_THE_BLANK: FillBlankQuestionForm,
        QuestionType.MATCH_THE_PAIR: MatchPairQuestionForm,
        QuestionType.TRUE_FALSE: TrueFalseQuestionForm,
        QuestionType.SHORT_ANSWER: ShortAnswerQuestionForm,
        QuestionType.LONG_ANSWER: LongAnswerQuestionForm,
        QuestionType.ASSERTION_REASON: AssertionReasonQuestionForm,
        QuestionType.CASE_BASED: CaseBasedQuestionForm,
        QuestionType.NUMERICAL_DYNAMIC: NumericalDynamicQuestionForm,
        QuestionType.ORDERING_SEQUENCING: OrderingSequencingQuestionForm,
        QuestionType.DIAGRAM_LABELLING: DiagramLabellingQuestionForm,
        QuestionType.SOURCE_BASED: SourceBasedQuestionForm,
    }

    assert len(type_to_cls) == 13

    for qtype, expected_cls in type_to_cls.items():
        node = QuestionNode(question_type=qtype, prompt_html=f"Prompt for {qtype.value}")
        form = create_question_form(node)
        assert isinstance(form, expected_cls), f"Failed for {qtype}: got {type(form)}, expected {expected_cls}"
        assert form.editor_prompt.get_plain_text().startswith("Prompt for")


# ============================================================================
# Optional Question Types Tests
# ============================================================================

def test_true_false_question_form(qapp: QApplication) -> None:
    """Test True / False form selection and justification requirement."""
    node = QuestionNode(
        question_type=QuestionType.TRUE_FALSE,
        type_data=TrueFalseData(correct_is_true=False, require_justification=True),
    )
    form = TrueFalseQuestionForm()
    form.load_question(node)

    assert form.rb_false.isChecked()
    assert form.chk_justification.isChecked()

    # Modify
    form.rb_true.setChecked(True)
    form.chk_justification.setChecked(False)
    form.save_to_question(node)

    assert isinstance(node.type_data, TrueFalseData)
    assert node.type_data.correct_is_true is True
    assert node.type_data.require_justification is False


def test_short_and_long_answer_forms(qapp: QApplication) -> None:
    """Test Short Answer keywords and Long Answer evaluation criteria."""
    # Short Answer
    s_node = QuestionNode(
        question_type=QuestionType.SHORT_ANSWER,
        type_data=ShortAnswerData(word_limit=60, expected_keywords=["Conservation", "Momentum"]),
    )
    s_form = ShortAnswerQuestionForm()
    s_form.load_question(s_node)

    assert s_form.spin_word_limit.value() == 60
    assert s_form.table_keywords.rowCount() == 2

    # Add keyword
    s_form.txt_keyword.setText("Elastic Collision")
    s_form._on_add_keyword()
    assert s_form.table_keywords.rowCount() == 3

    s_form.save_to_question(s_node)
    assert isinstance(s_node.type_data, ShortAnswerData)
    assert "Elastic Collision" in s_node.type_data.expected_keywords

    # Long Answer
    l_node = QuestionNode(
        question_type=QuestionType.LONG_ANSWER,
        type_data=LongAnswerData(word_limit=300, evaluation_criteria=["Concept (2M)", "Derivation (3M)"]),
    )
    l_form = LongAnswerQuestionForm()
    l_form.load_question(l_node)

    assert l_form.spin_word_limit.value() == 300
    assert l_form.table_criteria.rowCount() == 2

    # Add criterion
    l_form.txt_criterion.setText("Diagram & Graph (1M)")
    l_form._on_add_criterion()
    assert l_form.table_criteria.rowCount() == 3

    l_form.save_to_question(l_node)
    assert isinstance(l_node.type_data, LongAnswerData)
    assert "Diagram & Graph (1M)" in l_node.type_data.evaluation_criteria


def test_assertion_reason_form(qapp: QApplication) -> None:
    """Test Assertion & Reason dedicated fields and option preset selector."""
    node = QuestionNode(
        question_type=QuestionType.ASSERTION_REASON,
        type_data=AssertionReasonData(
            assertion_html="<p>Light bends when entering water.</p>",
            reason_html="<p>Light changes speed across media.</p>",
            correct_option_index=0,
        ),
    )
    form = AssertionReasonQuestionForm()
    form.load_question(node)

    assert "Light bends" in form.editor_assertion.get_plain_text()
    assert "changes speed" in form.editor_reason.get_plain_text()
    assert form.combo_correct.currentIndex() == 0

    # Switch correct option to (C)
    form.combo_correct.setCurrentIndex(2)
    form.save_to_question(node)

    assert isinstance(node.type_data, AssertionReasonData)
    assert node.type_data.correct_option_index == 2


def test_case_based_form(qapp: QApplication) -> None:
    """Test Case-Based comprehension title and passage editor."""
    node = QuestionNode(
        question_type=QuestionType.CASE_BASED,
        type_data=CaseBasedData(
            case_title="Semiconductor Physics",
            case_passage_html="<p>Doping silicon with phosphorus creates an n-type semiconductor.</p>",
        ),
    )
    form = CaseBasedQuestionForm()
    form.load_question(node)

    assert form.txt_title.text() == "Semiconductor Physics"
    assert "n-type" in form.editor_passage.get_plain_text()

    form.txt_title.setText("Modern Solid-State Physics")
    form.save_to_question(node)

    assert isinstance(node.type_data, CaseBasedData)
    assert node.type_data.case_title == "Modern Solid-State Physics"


def test_numerical_dynamic_form(qapp: QApplication) -> None:
    """Test Parameterized Numerical Dynamic formula solver and variable table."""
    node = QuestionNode(
        question_type=QuestionType.NUMERICAL_DYNAMIC,
        prompt_html="<p>Calculate potential energy: $U = m \\times g \\times h$.</p>",
        type_data=NumericalDynamicData(
            formula_expr="m * g * h",
            unit="J",
            answer_tolerance=0.05,
            variables={
                "m": NumericVariableRange(min_val=2.0, max_val=10.0, precision=1, step=1.0),
                "g": NumericVariableRange(min_val=9.8, max_val=9.8, precision=1, step=None),
                "h": NumericVariableRange(min_val=1.0, max_val=5.0, precision=1, step=0.5),
            },
        ),
    )
    form = NumericalDynamicQuestionForm()
    form.load_question(node)

    assert form.txt_formula.text() == "m * g * h"
    assert form.txt_unit.text() == "J"
    assert form.table_vars.rowCount() == 3

    # Test formula evaluation solver button
    form._on_test_formula()
    assert "✓ Valid Formula!" in form.lbl_calc_feedback.text()

    # Save back
    form.save_to_question(node)
    assert isinstance(node.type_data, NumericalDynamicData)
    assert "m" in node.type_data.variables
    assert "g" in node.type_data.variables


def test_ordering_sequencing_form(qapp: QApplication) -> None:
    """Test Ordering / Chronological Sequencing items and Move Up / Down actions."""
    node = QuestionNode(
        question_type=QuestionType.ORDERING_SEQUENCING,
        type_data=OrderingSequencingData(
            items=[
                OrderingItem(text_html="First Event", correct_position=1),
                OrderingItem(text_html="Second Event", correct_position=2),
                OrderingItem(text_html="Third Event", correct_position=3),
            ]
        ),
    )
    form = OrderingSequencingQuestionForm()
    form.load_question(node)

    assert form.table_items.rowCount() == 3
    assert form.table_items.item(0, 1).text() == "First Event"

    # Add item
    form._on_add_item()
    assert form.table_items.rowCount() == 4

    # Select row 1 and move up
    form.table_items.setCurrentCell(1, 1)
    form._on_move_up()
    assert form.table_items.item(0, 1).text() == "Second Event"

    form.save_to_question(node)
    assert isinstance(node.type_data, OrderingSequencingData)
    assert len(node.type_data.items) == 4


def test_diagram_labelling_form(qapp: QApplication) -> None:
    """Test Diagram Labelling image asset path and hotspots table."""
    node = QuestionNode(
        question_type=QuestionType.DIAGRAM_LABELLING,
        type_data=DiagramLabellingData(
            diagram_asset_path="assets/diagrams/cell.png",
            hotspots=[
                DiagramLabelHotspot(label_id="1", x_percent=30.0, y_percent=40.0, correct_term="Nucleus"),
                DiagramLabelHotspot(label_id="2", x_percent=60.0, y_percent=70.0, correct_term="Mitochondria"),
            ],
        ),
    )
    form = DiagramLabellingQuestionForm()
    form.load_question(node)

    assert form.txt_image.text() == "assets/diagrams/cell.png"
    assert form.table_hotspots.rowCount() == 2

    # Add hotspot
    form._on_add_hotspot()
    assert form.table_hotspots.rowCount() == 3

    form.save_to_question(node)
    assert isinstance(node.type_data, DiagramLabellingData)
    assert len(node.type_data.hotspots) == 3


def test_source_based_form(qapp: QApplication) -> None:
    """Test Source-Based citation and primary excerpt editing."""
    node = QuestionNode(
        question_type=QuestionType.SOURCE_BASED,
        type_data=SourceBasedData(
            source_citation="Constitution of India, Article 21",
            source_excerpt_html="<p>No person shall be deprived of his life or personal liberty...</p>",
        ),
    )
    form = SourceBasedQuestionForm()
    form.load_question(node)

    assert form.txt_citation.text() == "Constitution of India, Article 21"
    assert "personal liberty" in form.editor_excerpt.get_plain_text()

    form.txt_citation.setText("Universal Declaration of Human Rights")
    form.save_to_question(node)

    assert isinstance(node.type_data, SourceBasedData)
    assert node.type_data.source_citation == "Universal Declaration of Human Rights"


# ============================================================================
# Bilingual & Choice / Passage Dialog Tests
# ============================================================================

def test_bilingual_prompt_support(qapp: QApplication) -> None:
    """Test bilingual regional language prompt editor and drawer."""
    node = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Define electric flux.</p>",
        prompt_secondary_html="<p>विद्युत फ्लक्स को परिभाषित कीजिए।</p>",
    )
    form = NormalQuestionForm()
    form.load_question(node)

    assert not form.bilingual_drawer.isHidden()
    assert form.btn_toggle_bilingual.isChecked()
    assert "विद्युत फ्लक्स" in form.editor_prompt_secondary.get_plain_text()

    # Clear secondary prompt
    form.editor_prompt_secondary.set_html("")
    form.save_to_question(node)
    assert node.prompt_secondary_html is None


def test_choice_group_manager_dialog(qapp: QApplication, test_project: ProjectState) -> None:
    """Test ChoiceGroupManagerDialog creates OR choice pairs and Any K of N groups."""
    sec = test_project.sections[0]
    dlg = ChoiceGroupManagerDialog(sec, test_project)

    # Check 2 questions for an OR choice pair
    dlg.list_questions.item(0).setCheckState(Qt.CheckState.Checked)
    dlg.list_questions.item(1).setCheckState(Qt.CheckState.Checked)

    changed_fired = []
    dlg.groups_changed.connect(lambda: changed_fired.append(True))

    dlg._on_create_group()

    assert len(sec.choice_groups) == 1
    grp = sec.choice_groups[0]
    assert grp.rule_type == ChoiceRuleType.OR_PAIR
    assert sec.questions[0].choice_group_id == grp.choice_group_id
    assert sec.questions[1].choice_group_id == grp.choice_group_id
    assert len(changed_fired) == 1

    # Delete group
    dlg._on_delete_group(grp.choice_group_id)
    assert len(sec.choice_groups) == 0
    assert sec.questions[0].choice_group_id is None


def test_shared_passage_dialog(qapp: QApplication, test_project: ProjectState) -> None:
    """Test SharedPassageDialog creating and linking a stimulus passage to questions."""
    sec = test_project.sections[0]
    dlg = SharedPassageDialog(sec)

    dlg.txt_title.setText("Photosynthesis in C4 Plants")
    dlg.editor_content.set_html("<p>C4 plants minimize photorespiration by using PEP carboxylase...</p>")

    # Link to questions 2 and 3
    dlg.list_questions.item(1).setCheckState(Qt.CheckState.Checked)
    dlg.list_questions.item(2).setCheckState(Qt.CheckState.Checked)

    dlg._on_save()

    assert len(sec.shared_passages) == 1
    p = sec.shared_passages[0]
    assert p.title == "Photosynthesis in C4 Plants"
    assert sec.questions[1].shared_passage_id == p.passage_id
    assert sec.questions[2].shared_passage_id == p.passage_id
