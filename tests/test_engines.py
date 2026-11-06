"""Unit tests for Sub-phase 1.3: Marks Allocation Engine, Choices, Dynamic Numerics, & Analyzers."""

from __future__ import annotations

import pytest

from src.core.engine import (
    BlueprintValidator,
    DynamicNumericEngine,
    MarksEngine,
    QualityChecker,
    QualitySeverity,
    TimeEstimator,
)
from src.core.models import (
    BloomLevel,
    ChoiceGroup,
    ChoiceRuleType,
    DiagramAttachment,
    DifficultyLevel,
    ExamBlueprint,
    ExamMetadata,
    FillBlankData,
    MCQData,
    MCQOption,
    NumericalDynamicData,
    NumericVariableRange,
    ProjectState,
    QuestionNode,
    QuestionType,
    Section,
    TaxonomyMetadata,
)


def test_marks_parent_child_deduplication() -> None:
    """Verify that a parent question with children sums child marks and does NOT double-count parent marks."""
    # Parent question with nominal marks=10.0, but having two 5.0 children
    parent = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Parent Problem</p>",
        marks=10.0,
    )
    ch1 = QuestionNode(
        question_type=QuestionType.SHORT_ANSWER,
        prompt_html="<p>Part 1</p>",
        marks=5.0,
    )
    ch2 = QuestionNode(
        question_type=QuestionType.SHORT_ANSWER,
        prompt_html="<p>Part 2</p>",
        marks=5.0,
    )
    parent.add_child(ch1)
    parent.add_child(ch2)

    summary = MarksEngine.calculate_question_effective_marks(parent)
    assert summary.is_parent_composite is True
    assert summary.assigned_marks == 10.0
    assert summary.children_marks_sum == 10.0
    assert summary.effective_marks == 10.0  # Sum of children, NOT 10 + 5 + 5 = 20!

    sec = Section(title="Section A", questions=[parent])
    sec_summary = MarksEngine.calculate_section_marks(sec)
    assert sec_summary.total_effective_marks == 10.0
    assert sec_summary.total_available_marks == 10.0


def test_internal_choices_or_pair_and_any_k_of_n() -> None:
    """Verify OR choice groups count max mark and 'Any K of N' counts top K marks."""
    q1 = QuestionNode(prompt_html="<p>Q1</p>", marks=5.0)
    q2 = QuestionNode(prompt_html="<p>Q2</p>", marks=5.0)
    q3 = QuestionNode(prompt_html="<p>Q3</p>", marks=4.0)
    q4 = QuestionNode(prompt_html="<p>Q4</p>", marks=6.0)
    q5 = QuestionNode(prompt_html="<p>Q5</p>", marks=5.0)

    # Section with OR group (Q1 OR Q2: 5 Marks total, not 10)
    or_group = ChoiceGroup(
        rule_type=ChoiceRuleType.OR_PAIR,
        question_ids=[q1.question_id, q2.question_id],
    )
    # Any 2 of 3 group (Q3 [4M], Q4 [6M], Q5 [5M] -> top 2 sum = 6 + 5 = 11 Marks)
    any_k_group = ChoiceGroup(
        rule_type=ChoiceRuleType.ANY_K_OF_N,
        question_ids=[q3.question_id, q4.question_id, q5.question_id],
        attempt_count_k=2,
    )

    sec = Section(
        title="Electives",
        questions=[q1, q2, q3, q4, q5],
        choice_groups=[or_group, any_k_group],
    )

    sec_summary = MarksEngine.calculate_section_marks(sec)
    # Available marks = 5 + 5 + 4 + 6 + 5 = 25
    assert sec_summary.total_available_marks == 25.0
    # Effective marks = 5 (from OR) + 11 (from Any 2 of 3) = 16.0
    assert sec_summary.total_effective_marks == 16.0


def test_section_level_attempt_any_k_rule() -> None:
    """Verify Section.attempt_any_k limits ungrouped questions to top K marks."""
    questions = [
        QuestionNode(prompt_html=f"<p>Q{i}</p>", marks=float(i))
        for i in range(1, 6)  # Marks 1, 2, 3, 4, 5
    ]
    # Attempt any 3 out of 5: top 3 are 5 + 4 + 3 = 12 marks
    sec = Section(
        title="Short Answers",
        questions=questions,
        attempt_any_k=3,
    )
    sec_summary = MarksEngine.calculate_section_marks(sec)
    assert sec_summary.total_available_marks == 15.0
    assert sec_summary.total_effective_marks == 12.0


def test_paper_marks_discrepancy_audit() -> None:
    """Verify MarksEngine detects over-allocation and under-allocation against exam max_marks."""
    project = ProjectState(title="Final Exam")
    project.exam_metadata = ExamMetadata(max_marks=50.0)

    # 40 marks allocated (< 50 max_marks)
    q1 = QuestionNode(prompt_html="<p>Q1</p>", marks=40.0)
    project.sections[0].questions = [q1]

    report = MarksEngine.audit_project(project)
    assert report.total_effective_marks == 40.0
    assert report.has_discrepancy is True
    assert report.discrepancy_delta == -10.0
    assert "less than maximum marks" in (report.discrepancy_message or "")

    # Exact match: 50 marks
    q2 = QuestionNode(prompt_html="<p>Q2</p>", marks=10.0)
    project.sections[0].questions.append(q2)
    report_ok = MarksEngine.audit_project(project)
    assert report_ok.has_discrepancy is False
    assert report_ok.discrepancy_delta == 0.0

    # Over-allocation: 60 marks
    q3 = QuestionNode(prompt_html="<p>Q3</p>", marks=10.0)
    project.sections[0].questions.append(q3)
    report_over = MarksEngine.audit_project(project)
    assert report_over.has_discrepancy is True
    assert report_over.discrepancy_delta == 10.0
    assert "exceed maximum marks" in (report_over.discrepancy_message or "")


def test_dynamic_numeric_engine_evaluation_and_instantiation() -> None:
    """Verify seeded variable sampling, formula evaluation, and prompt token substitution."""
    data = NumericalDynamicData(
        variables={
            "mass": NumericVariableRange(min_val=10.0, max_val=20.0, precision=1, step=2.0),
            "acc": NumericVariableRange(min_val=2.0, max_val=5.0, precision=0),
        },
        formula_expr="mass * acc",
        unit="N",
        answer_tolerance=0.05,
    )
    prompt = "A cart of mass {{mass}} kg accelerates at {{acc}} m/s^2. Calculate force in {{unit}}."

    # Seeded instantiation yields deterministic results
    res1 = DynamicNumericEngine.instantiate_question(prompt, data, seed=42)
    res2 = DynamicNumericEngine.instantiate_question(prompt, data, seed=42)

    assert res1.variables == res2.variables
    assert res1.computed_answer == res2.computed_answer
    assert res1.computed_answer == res1.variables["mass"] * res1.variables["acc"]
    assert str(res1.formatted_variables["mass"]) in res1.instantiated_text
    assert str(res1.formatted_variables["acc"]) in res1.instantiated_text

    # Invalid formula injection protection
    with pytest.raises(ValueError):
        DynamicNumericEngine.evaluate_formula("__import__('os').system('dir')", {"x": 1.0})


def test_time_estimator_heuristic_and_explicit() -> None:
    """Verify TimeEstimator calculates question duration and compares to exam limit."""
    project = ProjectState(title="Timed Test")
    project.exam_metadata = ExamMetadata(duration_minutes=30)

    # 10 MCQ questions (~1.5 min each = ~15 mins)
    project.sections[0].questions = [
        QuestionNode(question_type=QuestionType.MCQ, prompt_html="<p>MCQ</p>", marks=1.0)
        for _ in range(10)
    ]
    report = TimeEstimator.analyze_project(project)
    assert 14.0 <= report.total_estimated_minutes <= 16.0
    assert report.status == "OK"

    # Add a massive long answer question (e.g. 50 minutes explicit)
    q_long = QuestionNode(
        question_type=QuestionType.LONG_ANSWER,
        prompt_html="<p>Write an essay</p>",
        marks=20.0,
        taxonomy_metadata=TaxonomyMetadata(estimated_time_mins=45.0),
    )
    project.sections[0].questions.append(q_long)
    report_over = TimeEstimator.analyze_project(project)
    assert report_over.total_estimated_minutes >= 60.0
    assert report_over.status == "OVER_TIME"


def test_quality_checker_detects_common_errors() -> None:
    """Verify QualityChecker identifies empty prompts, duplicates, missing keys, and low-DPI images."""
    project = ProjectState(title="Defective Paper")

    # 1. Empty prompt
    q_empty = QuestionNode(prompt_html="", marks=2.0)

    # 2. Duplicate prompt
    q_dup1 = QuestionNode(
        prompt_html="<p>Describe the primary functions of mitochondria in eukaryotic cells in detail.</p>",
        marks=5.0,
    )
    q_dup2 = QuestionNode(
        prompt_html="<p>Describe the primary functions of mitochondria in eukaryotic cells in detail.</p>",
        marks=5.0,
    )

    # 3. MCQ with missing key and duplicate options
    mcq_data = MCQData(
        options=[
            MCQOption(text_html="Identical Option", is_correct=False),
            MCQOption(text_html="Identical Option", is_correct=False),
        ]
    )
    q_mcq = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Choose the correct statement:</p>",
        marks=1.0,
        type_data=mcq_data,
    )

    # 4. Fill in the blank without placeholder
    blank_data = FillBlankData()
    q_blank = QuestionNode(
        question_type=QuestionType.FILL_IN_THE_BLANK,
        prompt_html="<p>This sentence has no blank</p>",
        marks=1.0,
        type_data=blank_data,
    )

    # 5. Low DPI image
    q_img = QuestionNode(
        prompt_html="<p>Analyze diagram</p>",
        marks=3.0,
        diagrams=[DiagramAttachment(asset_path="fig.png", dpi=72)],
    )

    project.sections[0].questions = [q_empty, q_dup1, q_dup2, q_mcq, q_blank, q_img]

    report = QualityChecker.audit_project(project)
    assert report.passed_cleanly is False
    codes = {issue.code for issue in report.issues}

    assert "EMPTY_PROMPT" in codes
    assert "DUPLICATE_QUESTION" in codes
    assert "DUPLICATE_MCQ_OPTION" in codes
    assert "MISSING_MCQ_KEY" in codes
    assert "MISSING_BLANK_PLACEHOLDER" in codes
    assert "LOW_DPI_IMAGE" in codes


def test_blueprint_validator_compliance_matrix() -> None:
    """Verify BlueprintValidator checks paper topic and difficulty distributions against target."""
    bp = ExamBlueprint(
        name="Physics Blueprint",
        total_marks_target=20.0,
        topic_marks_distribution={"Optics": 10.0, "Mechanics": 10.0},
        difficulty_marks_distribution={"Easy": 10.0, "Difficult": 10.0},
    )

    project = ProjectState(title="Blueprint Exam", blueprint=bp)

    # Question 1: Optics, Easy, 10 Marks
    q1 = QuestionNode(
        prompt_html="<p>Optics Problem</p>",
        marks=10.0,
        taxonomy_metadata=TaxonomyMetadata(
            topic="Optics",
            difficulty=DifficultyLevel.EASY,
        ),
    )
    # Question 2: Mechanics, Difficult, 10 Marks
    q2 = QuestionNode(
        prompt_html="<p>Mechanics Problem</p>",
        marks=10.0,
        taxonomy_metadata=TaxonomyMetadata(
            topic="Mechanics",
            difficulty=DifficultyLevel.DIFFICULT,
        ),
    )
    project.sections[0].questions = [q1, q2]

    report = BlueprintValidator.validate_project(project)
    assert report.overall_compliant is True
    assert report.actual_total_marks == 20.0

    # Introduce topic mismatch
    q2.taxonomy_metadata.topic = "Thermodynamics"
    report_mismatch = BlueprintValidator.validate_project(project)
    assert report_mismatch.overall_compliant is False
    assert any("Thermodynamics" in msg for msg in report_mismatch.summary_messages)
