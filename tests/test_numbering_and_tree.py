"""Unit tests for Sub-phase 1.2: Hierarchical Numbering FSM & Tree Manipulation Engine."""

from __future__ import annotations

import pytest

from src.core.engine import (
    NumberingFSM,
    QuestionTreeEngine,
    UndoRedoManager,
    format_index,
    int_to_alpha,
    int_to_roman,
)
from src.core.models import (
    MCQData,
    NumberingStyle,
    ProjectState,
    QuestionNode,
    QuestionType,
    Section,
)


def test_roman_and_alpha_formatters() -> None:
    """Verify conversion helpers for Roman numerals, alphabetic indices, and custom prefixes/suffixes."""
    assert int_to_roman(1, uppercase=True) == "I"
    assert int_to_roman(4, uppercase=True) == "IV"
    assert int_to_roman(9, uppercase=False) == "ix"
    assert int_to_roman(14, uppercase=True) == "XIV"

    assert int_to_alpha(1, uppercase=True) == "A"
    assert int_to_alpha(26, uppercase=False) == "z"
    assert int_to_alpha(27, uppercase=True) == "AA"

    assert format_index(1, NumberingStyle.NUMERIC, prefix="Q", suffix=".") == "Q1."
    assert format_index(2, NumberingStyle.LOWER_ALPHA, prefix="(", suffix=")") == "(b)"
    assert format_index(3, NumberingStyle.LOWER_ROMAN, prefix="[", suffix="]") == "[iii]"
    assert format_index(4, NumberingStyle.UPPER_ROMAN, prefix="", suffix=".") == "IV."


def test_recursive_dfs_numbering_and_manual_override() -> None:
    """Verify multi-level numbering across Parent -> Minor -> Subquestion -> Further Subquestion and manual overrides."""
    project = ProjectState(title="Hierarchy Numbering Test")
    sec = project.sections[0]
    sec.question_numbering_prefix = "Q"
    sec.question_numbering_suffix = "."

    q1 = QuestionTreeEngine.add_parent_question(
        project,
        QuestionNode(prompt_html="<p>Parent 1</p>", child_numbering_style=NumberingStyle.LOWER_ALPHA),
    )
    q1_a = QuestionTreeEngine.add_child_question(
        project,
        q1.question_id,
        QuestionNode(prompt_html="<p>Minor 1(a)</p>", child_numbering_style=NumberingStyle.LOWER_ROMAN),
    )
    q1_b = QuestionTreeEngine.add_child_question(
        project,
        q1.question_id,
        QuestionNode(prompt_html="<p>Minor 1(b)</p>", child_numbering_style=NumberingStyle.LOWER_ROMAN),
    )
    q1_a_i = QuestionTreeEngine.add_child_question(
        project,
        q1_a.question_id,
        QuestionNode(prompt_html="<p>Sub 1(a)(i)</p>", child_numbering_style=NumberingStyle.NUMERIC),
    )
    q1_a_i_1 = QuestionTreeEngine.add_child_question(
        project,
        q1_a_i.question_id,
        QuestionNode(prompt_html="<p>Further Sub 1(a)(i)(1)</p>"),
    )

    q2 = QuestionTreeEngine.add_parent_question(
        project,
        QuestionNode(prompt_html="<p>Parent 2 with override</p>", numbering_override="Q2*"),
    )
    q3 = QuestionTreeEngine.add_parent_question(
        project,
        QuestionNode(prompt_html="<p>Parent 3</p>"),
    )

    assert q1.resolved_number == "Q1."
    assert q1_a.resolved_number == "(a)"
    assert q1_b.resolved_number == "(b)"
    assert q1_a_i.resolved_number == "(i)"
    assert q1_a_i_1.resolved_number == "(1)"
    # Manual override on Q2 does not break sibling counter for Q3
    assert q2.resolved_number == "Q2*"
    assert q3.resolved_number == "Q3."


def test_tree_mutations_insert_reorder_reparent_cross_section_duplicate_delete() -> None:
    """Verify numbering updates dynamically on insert, delete, move up/down, reparent, cross-section move, and duplicate."""
    sec_a = Section(
        title="Section A",
        is_default_unsectioned=False,
        question_numbering_prefix="Q",
        question_numbering_suffix=".",
    )
    sec_b = Section(
        title="Section B",
        is_default_unsectioned=False,
        question_numbering_prefix="Q",
        question_numbering_suffix=".",
        continue_numbering_from_previous=True,
    )
    project = ProjectState(title="Tree Mutation Test", sections=[sec_a, sec_b])

    q1 = QuestionTreeEngine.add_parent_question(project, QuestionNode(prompt_html="First"), section_id=sec_a.section_id)
    q2 = QuestionTreeEngine.add_parent_question(project, QuestionNode(prompt_html="Second"), section_id=sec_a.section_id)
    q3 = QuestionTreeEngine.add_parent_question(project, QuestionNode(prompt_html="Third"), section_id=sec_b.section_id)

    assert [q1.resolved_number, q2.resolved_number, q3.resolved_number] == ["Q1.", "Q2.", "Q3."]

    # Reorder Q2 up above Q1
    moved = QuestionTreeEngine.move_up(project, q2.question_id)
    assert moved is True
    assert q2.resolved_number == "Q1."
    assert q1.resolved_number == "Q2."

    # Move Q2 back down
    moved_down = QuestionTreeEngine.move_down(project, q2.question_id)
    assert moved_down is True
    assert q1.resolved_number == "Q1."
    assert q2.resolved_number == "Q2."

    # Drag-and-drop reparent: make Q2 a child subquestion of Q1
    QuestionTreeEngine.reparent_node(project, q2.question_id, new_parent_id=q1.question_id)
    assert q2.parent_id == q1.question_id
    assert q2.resolved_number == "(a)"
    # Q3 in Section B automatically renumbers from Q3. to Q2.!
    assert q3.resolved_number == "Q2."

    # Prevent cyclic reparenting (cannot reparent Q1 into its own child Q2)
    with pytest.raises(ValueError):
        QuestionTreeEngine.reparent_node(project, q1.question_id, new_parent_id=q2.question_id)

    # Duplicate Q1 (with its child Q2)
    duplicated_q1 = QuestionTreeEngine.duplicate_node(project, q1.question_id)
    assert duplicated_q1.question_id != q1.question_id
    assert len(duplicated_q1.children) == 1
    assert duplicated_q1.children[0].question_id != q2.question_id
    assert duplicated_q1.resolved_number == "Q2."
    assert duplicated_q1.children[0].resolved_number == "(a)"
    assert q3.resolved_number == "Q3."

    # Move duplicated_q1 across sections to Section B at index 0
    QuestionTreeEngine.move_to_section(
        project,
        duplicated_q1.question_id,
        target_section_id=sec_b.section_id,
        target_index=0,
    )
    assert duplicated_q1.section_id == sec_b.section_id
    assert sec_b.questions[0].question_id == duplicated_q1.question_id

    # Delete check: deleting a parent with children when allow_with_children=False raises ValueError
    with pytest.raises(ValueError):
        QuestionTreeEngine.delete_node(project, duplicated_q1.question_id, allow_with_children=False)

    removed_node, child_count = QuestionTreeEngine.delete_node(
        project, duplicated_q1.question_id, allow_with_children=True
    )
    assert removed_node.question_id == duplicated_q1.question_id
    assert child_count == 1
    assert q3.resolved_number == "Q2."


def test_undo_redo_manager_preserves_hierarchy_options_and_marks() -> None:
    """Verify UndoRedoManager restores complete hierarchy, MCQ options, marks, and resolved numbering."""
    project = ProjectState(title="Undo Redo Test")
    undo_mgr = UndoRedoManager()

    # Initial empty state snapshot
    undo_mgr.record_state(project, "Initial Empty State")

    mcq = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Capital of India?</p>",
        marks=2.0,
    )
    assert isinstance(mcq.type_data, MCQData)
    mcq.type_data.options[0].text_html = "Mumbai"
    mcq.type_data.add_option("New Delhi", is_correct=True)

    QuestionTreeEngine.add_parent_question(project, mcq)
    undo_mgr.record_state(project, "Add MCQ Question")

    child = QuestionTreeEngine.add_child_question(
        project,
        mcq.question_id,
        QuestionNode(prompt_html="<p>State its population</p>", marks=3.0),
    )
    undo_mgr.record_state(project, "Add Child Subquestion")

    assert len(project.all_questions_dfs()) == 2
    assert child.resolved_number == "(a)"

    # Undo adding child subquestion
    project = undo_mgr.undo(project)
    assert len(project.all_questions_dfs()) == 1
    restored_mcq = project.sections[0].questions[0]
    assert restored_mcq.marks == 2.0
    assert isinstance(restored_mcq.type_data, MCQData)
    assert len(restored_mcq.type_data.options) == 2
    assert restored_mcq.type_data.options[1].text_html == "New Delhi"
    assert restored_mcq.type_data.options[1].is_correct is True

    # Undo adding MCQ question back to empty state
    project = undo_mgr.undo(project)
    assert len(project.all_questions_dfs()) == 0

    # Redo step 1 (MCQ restored)
    project = undo_mgr.redo(project)
    assert len(project.all_questions_dfs()) == 1
    assert project.sections[0].questions[0].resolved_number == "1."

    # Redo step 2 (Child subquestion restored)
    project = undo_mgr.redo(project)
    assert len(project.all_questions_dfs()) == 2
    assert project.sections[0].questions[0].children[0].resolved_number == "(a)"
    assert project.sections[0].questions[0].children[0].marks == 3.0
