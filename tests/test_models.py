"""Unit tests for Sub-phase 1.1: Domain Data Models & Schema Serialization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.models import (
    AssertionReasonData,
    BilingualLayout,
    BloomLevel,
    BlueprintTargetCell,
    CandidateFieldType,
    CanvasElement,
    CanvasElementType,
    CaseBasedData,
    ChoiceGroup,
    ChoiceRuleType,
    DiagramAttachment,
    DiagramLabelHotspot,
    DiagramLabellingData,
    DifficultyLevel,
    ExamBlueprint,
    ExamMetadata,
    FillBlankData,
    FillBlankMode,
    LongAnswerData,
    MCQData,
    MCQOptionLayout,
    Margins,
    MarkingScheme,
    MatchPairData,
    NumberingStyle,
    NumericVariableRange,
    NumericalDynamicData,
    OrderingItem,
    OrderingSequencingData,
    Orientation,
    PageSetup,
    PageSize,
    PatternPreset,
    ProjectState,
    QuestionNode,
    QuestionType,
    SecondaryLanguage,
    Section,
    SectionPresetSpec,
    SharedPassage,
    ShortAnswerData,
    SourceBasedData,
    StepPoint,
    TaxonomyMetadata,
    Template,
    TextAlignment,
    TrueFalseData,
)


def test_enums_core_vs_optional_partition() -> None:
    """Verify 4 core question types and 9 optional question types partition all 13 types cleanly."""
    core = QuestionType.core_types()
    optional = QuestionType.optional_types()
    assert len(core) == 4
    assert len(optional) == 9
    assert set(core).isdisjoint(set(optional))
    assert len(set(core) | set(optional)) == len(QuestionType)
    for qt in core:
        assert qt.is_core is True
    for qt in optional:
        assert qt.is_core is False


def test_page_setup_dimensions_and_coordinate_validation() -> None:
    """Verify page dimensions across A4/A3/Letter/Custom, Portrait/Landscape, and invalid margin rejection."""
    setup_a4 = PageSetup(size=PageSize.A4, orientation=Orientation.PORTRAIT)
    assert setup_a4.effective_dimensions_mm == (210.0, 297.0)
    assert setup_a4.printable_width_mm == 180.0
    assert setup_a4.printable_height_mm == 267.0

    setup_a4_land = PageSetup(size=PageSize.A4, orientation=Orientation.LANDSCAPE)
    assert setup_a4_land.effective_dimensions_mm == (297.0, 210.0)

    setup_custom = PageSetup(
        size=PageSize.CUSTOM,
        custom_width_mm=200.0,
        custom_height_mm=300.0,
        margins_mm=Margins(top=10.0, bottom=10.0, left=12.0, right=12.0),
    )
    assert setup_custom.printable_width_mm == 176.0
    assert setup_custom.printable_height_mm == 280.0

    with pytest.raises(ValidationError):
        PageSetup(
            size=PageSize.A4,
            margins_mm=Margins(left=95.0, right=95.0, top=15.0, bottom=15.0),
        )


def test_template_coordinate_validation_and_snapshot_isolation() -> None:
    """Verify template zone bounds validation and complete snapshot isolation from source template mutations."""
    header_el = CanvasElement(
        element_type=CanvasElementType.TEXT,
        x_mm=10.0,
        y_mm=5.0,
        width_mm=160.0,
        height_mm=10.0,
        content="{{exam_name}} - {{subject_name}}",
        bold=True,
        alignment=TextAlignment.CENTER,
    )
    template = Template(
        name="University Header Template",
        header_height_mm=40.0,
        footer_height_mm=15.0,
        different_first_page=True,
        first_page_header_elements=[header_el],
    )

    project = ProjectState.create_from_template(template, title="Midterm Physics")

    # Mutate original template
    template.name = "Mutated Template Name"
    template.first_page_header_elements[0].content = "CHANGED CONTENT"
    template.header_height_mm = 55.0

    # Verify embedded project snapshot is 100% isolated
    assert project.template_snapshot.name == "University Header Template"
    assert project.template_snapshot.first_page_header_elements[0].content == "{{exam_name}} - {{subject_name}}"
    assert project.template_snapshot.header_height_mm == 40.0

    # Out-of-bounds element coordinate raises ValidationError
    with pytest.raises(ValidationError):
        Template(
            header_height_mm=30.0,
            running_header_elements=[
                CanvasElement(x_mm=5.0, y_mm=35.0, width_mm=20.0, height_mm=5.0)
            ],
        )


def test_mcq_data_invariants_and_finalization_validation() -> None:
    """Verify MCQ starts with 1 default option box, auto-labels A/B/C/D, and enforces >=2 options on finalize."""
    q_mcq = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>What is the SI unit of force?</p>",
        marks=1.0,
    )
    assert isinstance(q_mcq.type_data, MCQData)
    assert len(q_mcq.type_data.options) == 1
    assert q_mcq.type_data.options[0].label == "A"

    # Finalization fails when only 1 option exists
    errors_initial = q_mcq.validate_node(finalize=True)
    assert len(errors_initial) >= 1

    # Populate first option and add 3 more options
    q_mcq.type_data.options[0].text_html = "Newton"
    q_mcq.type_data.options[0].is_correct = True
    opt_b = q_mcq.type_data.add_option("Joule", is_correct=False)
    opt_c = q_mcq.type_data.add_option("Watt", is_correct=False)
    opt_d = q_mcq.type_data.add_option("Pascal", is_correct=False)

    assert [o.label for o in q_mcq.type_data.options] == ["A", "B", "C", "D"]
    assert q_mcq.validate_node(finalize=True) == []

    # Remove option B and verify automatic relabeling to A, B, C
    q_mcq.type_data.remove_option(opt_b.id)
    assert [o.label for o in q_mcq.type_data.options] == ["A", "B", "C"]
    assert [o.id for o in q_mcq.type_data.options] == [
        q_mcq.type_data.options[0].id,
        opt_c.id,
        opt_d.id,
    ]


def test_match_pair_invariants() -> None:
    """Verify Match the Pair defaults to 2 rows, supports adding/removing rows, and preserves ground-truth mapping."""
    q_match = QuestionNode(
        question_type=QuestionType.MATCH_THE_PAIR,
        prompt_html="<p>Match the scientist with their discovery:</p>",
        marks=4.0,
    )
    assert isinstance(q_match.type_data, MatchPairData)
    assert len(q_match.type_data.rows) == 2

    q_match.type_data.rows[0].col_a_html = "Einstein"
    q_match.type_data.rows[0].col_b_html = "Relativity"
    q_match.type_data.rows[1].col_a_html = "Newton"
    q_match.type_data.rows[1].col_b_html = "Gravitation"

    row3 = q_match.type_data.add_row("Faraday", "Electromagnetic Induction")
    assert len(q_match.type_data.rows) == 3
    assert q_match.type_data.ground_truth_mapping() == {1: 1, 2: 2, 3: 3}

    q_match.type_data.remove_row(row3.id)
    assert len(q_match.type_data.rows) == 2

    # Remove down to 1 row, then verify removing the last row raises ValueError
    q_match.type_data.remove_row(q_match.type_data.rows[1].id)
    with pytest.raises(ValueError):
        q_match.type_data.remove_row(q_match.type_data.rows[0].id)


def test_deep_hierarchy_and_all_13_question_types_serialization() -> None:
    """Verify 4-level recursive question hierarchy and JSON round-trip across all 13 question types."""
    project = ProjectState(title="Comprehensive Engineering Exam")
    project.exam_metadata = ExamMetadata(
        exam_name="End Semester Examination",
        subject_name="Applied Mechanics & Computing",
        subject_code="ME-101",
        class_semester="B.Tech Sem I",
        exam_date="2026-11-15",
        duration_minutes=180,
        max_marks=100.0,
        set_identifier="Set A",
        candidate_fields=[CandidateFieldType.STUDENT_NAME, CandidateFieldType.ROLL_NO],
        watermark_text="CONFIDENTIAL",
    )
    project.layout_settings.bilingual_mode = True
    project.layout_settings.secondary_language = SecondaryLanguage.HINDI
    project.layout_settings.bilingual_layout = BilingualLayout.SIDE_BY_SIDE

    sec = Section(
        title="Section A",
        instructions_html="<p>Attempt all questions.</p>",
        is_default_unsectioned=False,
    )

    # 4-level deep hierarchy: Parent -> Minor -> Subquestion -> Further Subquestion
    parent_q = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Main Question 1</p>",
        prompt_secondary_html="<p>मुख्य प्रश्न १</p>",
    )
    minor_q = parent_q.add_child(
        QuestionNode(question_type=QuestionType.SHORT_ANSWER, prompt_html="<p>Minor 1(a)</p>")
    )
    sub_q = minor_q.add_child(
        QuestionNode(question_type=QuestionType.TRUE_FALSE, prompt_html="<p>Sub 1(a)(i)</p>", marks=2.0)
    )
    further_sub_q = sub_q.add_child(
        QuestionNode(
            question_type=QuestionType.FILL_IN_THE_BLANK,
            prompt_html="<p>Further Sub 1(a)(i)(1): Force = mass × ___</p>",
            marks=1.0,
            type_data=FillBlankData(
                mode=FillBlankMode.WITH_OPTIONS,
                word_bank_options=["acceleration", "velocity", "momentum"],
            ),
        )
    )
    sec.add_question(parent_q)

    # Instantiate every remaining question type to verify polymorphic round-trip
    all_other_types = [
        (QuestionType.MCQ, MCQData(option_layout=MCQOptionLayout.INLINE)),
        (QuestionType.MATCH_THE_PAIR, MatchPairData()),
        (QuestionType.LONG_ANSWER, LongAnswerData(word_limit=400)),
        (QuestionType.ASSERTION_REASON, AssertionReasonData(assertion_html="A", reason_html="R", correct_option_index=1)),
        (QuestionType.CASE_BASED, CaseBasedData(case_title="Thermodynamics Case", case_passage_html="<p>Passage</p>")),
        (
            QuestionType.NUMERICAL_DYNAMIC,
            NumericalDynamicData(
                variables={"m": NumericVariableRange(min_val=2.0, max_val=10.0, precision=1)},
                formula_expr="m * 9.81",
                unit="N",
            ),
        ),
        (
            QuestionType.ORDERING_SEQUENCING,
            OrderingSequencingData(items=[OrderingItem(text_html="Step 1", correct_position=1)]),
        ),
        (
            QuestionType.DIAGRAM_LABELLING,
            DiagramLabellingData(
                diagram_asset_path="assets/heart.png",
                hotspots=[DiagramLabelHotspot(label_id="1", x_percent=25.0, y_percent=60.0, correct_term="Aorta")],
            ),
        ),
        (
            QuestionType.SOURCE_BASED,
            SourceBasedData(source_excerpt_html="<blockquote>Historical excerpt</blockquote>", source_citation="1947 Archive"),
        ),
    ]

    for qt, tdata in all_other_types:
        node = QuestionNode(
            question_type=qt,
            prompt_html=f"<p>Sample {qt.value}</p>",
            marks=5.0,
            type_data=tdata,
            diagrams=[DiagramAttachment(asset_path="assets/fig1.png", width_mm=50.0, height_mm=30.0)],
            marking_scheme=MarkingScheme(
                model_answer_html="<p>Solution</p>",
                step_points=[StepPoint(description="Formula", marks=2.0)],
            ),
            taxonomy_metadata=TaxonomyMetadata(
                subject="Physics",
                topic="Mechanics",
                difficulty=DifficultyLevel.MODERATE,
                bloom_level=BloomLevel.APPLY,
                tags=["kinematics", "forces"],
                estimated_time_mins=5.0,
            ),
        )
        sec.add_question(node)

    sec.choice_groups.append(
        ChoiceGroup(
            rule_type=ChoiceRuleType.OR_PAIR,
            question_ids=[sec.questions[0].question_id, sec.questions[1].question_id],
        )
    )
    sec.shared_passages.append(
        SharedPassage(
            title="Shared Reading Stimulus",
            content_html="<p>Read carefully.</p>",
            linked_question_ids=[sec.questions[0].question_id],
        )
    )
    project.sections = [sec]
    project.blueprint = ExamBlueprint(
        name="100-Mark Blueprint",
        total_marks_target=100.0,
        topic_marks_distribution={"Mechanics": 50.0},
        matrix_cells=[
            BlueprintTargetCell(
                topic="Mechanics",
                question_type=QuestionType.MCQ,
                difficulty=DifficultyLevel.EASY,
                bloom_level=BloomLevel.REMEMBER,
                target_marks=10.0,
            )
        ],
    )

    preset = PatternPreset(
        name="University Pattern",
        sections=[SectionPresetSpec(title="Part I", question_count=10, marks_per_question=2.0)],
    )
    assert preset.max_marks == 80.0

    # Round-trip serialize and deserialize
    json_payload = project.to_json_string()
    restored = ProjectState.from_json_string(json_payload)

    assert restored.project_id == project.project_id
    assert restored.title == "Comprehensive Engineering Exam"
    assert restored.uses_explicit_sections is True
    assert len(restored.all_questions_dfs()) == 13
    assert restored.sections[0].questions[0].children[0].children[0].children[0].question_id == further_sub_q.question_id

    placeholder_ctx = restored.exam_metadata.to_placeholder_context(page_number="2", total_pages="5")
    assert placeholder_ctx["{{exam_name}}"] == "End Semester Examination"
    assert placeholder_ctx["{{duration}}"] == "3 hrs"
    assert placeholder_ctx["{{max_marks}}"] == "100"
    assert placeholder_ctx["{{page_number}}"] == "2"
    assert placeholder_ctx["{{total_pages}}"] == "5"
