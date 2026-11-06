"""Unit tests for Sub-phase 2.2: Semantic HTML5 & CSS Paged Media Compiler + PDF Exporter."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from src.core.models import (
    AssertionReasonData,
    BilingualLayout,
    BlankItem,
    CandidateFieldType,
    CaseBasedData,
    ChoiceGroup,
    ChoiceRuleType,
    DiagramLabelHotspot,
    DiagramLabellingData,
    ExamMetadata,
    FillBlankData,
    FillBlankMode,
    LongAnswerData,
    MCQData,
    MarkingScheme,
    MatchPairData,
    NumericVariableRange,
    NumericalDynamicData,
    OrderingItem,
    OrderingSequencingData,
    Orientation,
    PageSize,
    ProjectState,
    QuestionNode,
    QuestionType,
    SecondaryLanguage,
    Section,
    SharedPassage,
    ShortAnswerData,
    SourceBasedData,
    StepPoint,
    TrueFalseData,
)
from src.core.storage import TemplateStore
from src.rendering import (
    CSSGenerator,
    HTMLCompiler,
    PDFExporter,
    SupplementaryBuilder,
)


def _build_comprehensive_project() -> ProjectState:
    store = TemplateStore()
    tmpl = store.list_templates()[0]
    project = ProjectState.create_from_template(tmpl, title="Midterm Physics & Computing")
    project.exam_metadata = ExamMetadata(
        exam_name="MIDTERM EXAMINATION 2026",
        subject_name="Applied Physics",
        subject_code="PH-204",
        class_semester="B.Sc. Sem III",
        exam_date="2026-11-20",
        duration_minutes=120,
        max_marks=50.0,
        set_identifier="Set A",
        general_instructions="<p>All questions are compulsory unless internal choice is indicated.</p>",
        candidate_fields=[
            CandidateFieldType.STUDENT_NAME,
            CandidateFieldType.ROLL_NO,
            CandidateFieldType.STUDENT_SIGNATURE,
            CandidateFieldType.INVIGILATOR_SIGNATURE,
        ],
        watermark_text="CONFIDENTIAL",
    )
    project.layout_settings.bilingual_mode = True
    project.layout_settings.secondary_language = SecondaryLanguage.HINDI
    project.layout_settings.bilingual_layout = BilingualLayout.SIDE_BY_SIDE

    sec = Section(
        title="Section A — Core & Objective",
        instructions_html="<p>Answer carefully.</p>",
        is_default_unsectioned=False,
    )

    # 1. Normal Question with LaTeX equation, bilingual prompt, answer lines, and rubric
    q_norm = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html=r"<p>State Einstein's mass-energy equivalence relation $E = mc^2$.</p>",
        prompt_secondary_html="<p>आइंस्टीन का द्रव्यमान-ऊर्जा संबंध लिखिए।</p>",
        marks=3.0,
        answer_space_lines=3,
        marking_scheme=MarkingScheme(
            model_answer_html="<p>SECRET_MODEL_ANSWER_E_MC2</p>",
            step_points=[StepPoint(description="Formula statement", marks=2.0), StepPoint(description="SI units", marks=1.0)],
            alternative_answers=["Energy equals mass times speed of light squared"],
            rubric_notes="Award full marks if symbols are defined.",
        ),
    )
    sec.add_question(q_norm)

    # 2. MCQ Question
    mcq_data = MCQData()
    mcq_data.options[0].text_html = "Ohm"
    mcq_data.add_option("Tesla", is_correct=True)
    mcq_data.add_option("Weber", is_correct=False)
    mcq_data.add_option("Henry", is_correct=False)
    q_mcq = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>Which of the following is the SI unit of magnetic flux density?</p>",
        marks=1.0,
        type_data=mcq_data,
    )
    sec.add_question(q_mcq)

    # 3. Fill in the Blank with Word Bank
    q_fib = QuestionNode(
        question_type=QuestionType.FILL_IN_THE_BLANK,
        prompt_html="<p>The rate of change of momentum is directly proportional to ___.</p>",
        marks=1.0,
        type_data=FillBlankData(
            mode=FillBlankMode.WITH_OPTIONS,
            blanks=[BlankItem(blank_index=1, correct_answer="SECRET_APPLIED_FORCE")],
            word_bank_options=["applied force", "inertia", "impulse"],
        ),
    )
    sec.add_question(q_fib)

    # 4. Match the Pair
    mp_data = MatchPairData()
    mp_data.rows[0].col_a_html = "Coulomb's Law"
    mp_data.rows[0].col_b_html = "Electrostatics"
    mp_data.rows[1].col_a_html = "Faraday's Law"
    mp_data.rows[1].col_b_html = "Electromagnetic Induction"
    q_match = QuestionNode(
        question_type=QuestionType.MATCH_THE_PAIR,
        prompt_html="<p>Match the physical laws with their domains:</p>",
        marks=2.0,
        type_data=mp_data,
    )
    sec.add_question(q_match)

    # 5. All 9 Optional Question Types
    opt_questions = [
        QuestionNode(
            question_type=QuestionType.TRUE_FALSE,
            prompt_html="<p>Sound waves can travel through a vacuum.</p>",
            marks=1.0,
            type_data=TrueFalseData(correct_is_true=False, require_justification=True),
        ),
        QuestionNode(
            question_type=QuestionType.SHORT_ANSWER,
            prompt_html="<p>Define total internal reflection.</p>",
            marks=2.0,
            type_data=ShortAnswerData(word_limit=40),
        ),
        QuestionNode(
            question_type=QuestionType.LONG_ANSWER,
            prompt_html="<p>Derive Maxwell's wave equation in free space.</p>",
            marks=5.0,
            type_data=LongAnswerData(word_limit=250),
        ),
        QuestionNode(
            question_type=QuestionType.ASSERTION_REASON,
            prompt_html="<p>Evaluate the assertion and reason:</p>",
            marks=2.0,
            type_data=AssertionReasonData(
                assertion_html="Metals are good conductors of electricity.",
                reason_html="Metals possess a high density of free electrons.",
                correct_option_index=0,
            ),
        ),
        QuestionNode(
            question_type=QuestionType.CASE_BASED,
            prompt_html="<p>Based on the case above, calculate the efficiency.</p>",
            marks=4.0,
            type_data=CaseBasedData(
                case_title="Carnot Heat Engine",
                case_passage_html="<p>A reversible engine operates between two reservoirs.</p>",
            ),
        ),
        QuestionNode(
            question_type=QuestionType.NUMERICAL_DYNAMIC,
            prompt_html="<p>A resistor of {{R}} Ohm carries a current of {{I}} A. Find voltage.</p>",
            marks=3.0,
            type_data=NumericalDynamicData(
                variables={
                    "R": NumericVariableRange(min_val=5.0, max_val=15.0, precision=0),
                    "I": NumericVariableRange(min_val=2.0, max_val=6.0, precision=0),
                },
                formula_expr="R * I",
                unit="V",
            ),
        ),
        QuestionNode(
            question_type=QuestionType.ORDERING_SEQUENCING,
            prompt_html="<p>Arrange the electromagnetic spectrum in increasing order of frequency:</p>",
            marks=2.0,
            type_data=OrderingSequencingData(
                items=[
                    OrderingItem(text_html="Radio waves", correct_position=1),
                    OrderingItem(text_html="Visible light", correct_position=2),
                    OrderingItem(text_html="Gamma rays", correct_position=3),
                ]
            ),
        ),
        QuestionNode(
            question_type=QuestionType.DIAGRAM_LABELLING,
            prompt_html="<p>Identify the numbered parts of the optical fiber:</p>",
            marks=2.0,
            type_data=DiagramLabellingData(
                hotspots=[
                    DiagramLabelHotspot(label_id="1", x_percent=30.0, y_percent=50.0, correct_term="Core"),
                    DiagramLabelHotspot(label_id="2", x_percent=70.0, y_percent=50.0, correct_term="Cladding"),
                ]
            ),
        ),
        QuestionNode(
            question_type=QuestionType.SOURCE_BASED,
            prompt_html="<p>Interpret the historical scientific excerpt:</p>",
            marks=3.0,
            type_data=SourceBasedData(
                source_excerpt_html="<blockquote>On the Electrodynamics of Moving Bodies</blockquote>",
                source_citation="A. Einstein, 1905",
            ),
        ),
    ]
    for oq in opt_questions:
        sec.add_question(oq)

    # Link a SharedPassage and an OR ChoiceGroup
    sec.shared_passages.append(
        SharedPassage(
            title="Passage 1: Semiconductor Physics",
            content_html="<p>Intrinsic semiconductors have equal electron and hole concentrations.</p>",
            linked_question_ids=[q_norm.question_id],
        )
    )
    sec.choice_groups.append(
        ChoiceGroup(
            rule_type=ChoiceRuleType.OR_PAIR,
            question_ids=[opt_questions[1].question_id, opt_questions[2].question_id],
            label_text="OR",
        )
    )

    project.sections = [sec]
    return project


def test_css_paged_media_and_page_break_rules() -> None:
    """Verify `@page` geometry, `@page :first`, column layouts, and `break-inside: avoid` rules."""
    project = _build_comprehensive_project()
    project.template_snapshot.page_setup.size = PageSize.CUSTOM
    project.template_snapshot.page_setup.custom_width_mm = 205.0
    project.template_snapshot.page_setup.custom_height_mm = 290.0
    project.template_snapshot.page_setup.orientation = Orientation.LANDSCAPE

    css = CSSGenerator.generate_stylesheet(project, preview_sheet_framing=True)
    assert "@page {" in css
    assert "@page :first {" in css
    assert "size: 290.0mm 205.0mm;" in css
    assert ".question-block {" in css
    assert "break-inside: avoid;" in css
    assert "break-after: avoid;" in css
    assert "@font-face" in css
    assert "Noto Sans Devanagari" in css


def test_student_view_hides_answers_while_teacher_preview_shows_keys() -> None:
    """Verify Student View completely omits model answers and MCQ keys, whereas Teacher Preview includes them."""
    project = _build_comprehensive_project()

    student_html = HTMLCompiler.compile_project(project, teacher_preview_mode=False)
    teacher_html = HTMLCompiler.compile_project(project, teacher_preview_mode=True)

    # Common structural elements present in both
    for doc_html in (student_html, teacher_html):
        assert "MIDTERM EXAMINATION 2026" in doc_html
        assert "<math" in doc_html  # LaTeX $E = mc^2$ converted to MathML
        assert "आइंस्टीन का द्रव्यमान-ऊर्जा संबंध लिखिए।" in doc_html  # Devanagari rendered
        assert "bilingual-side-by-side" in doc_html
        assert "CONFIDENTIAL" in doc_html
        assert "Student Name" in doc_html
        assert "Passage 1: Semiconductor Physics" in doc_html
        assert "— OR —" in doc_html

    # Student view must NOT leak secret answers or teacher key badges
    assert "SECRET_MODEL_ANSWER_E_MC2" not in student_html
    assert "SECRET_APPLIED_FORCE" not in student_html
    assert 'class="teacher-key-badge"' not in student_html

    # Teacher preview MUST display model answers, MCQ keys, and rubrics
    assert "SECRET_MODEL_ANSWER_E_MC2" in teacher_html
    assert "SECRET_APPLIED_FORCE" in teacher_html
    assert 'class="teacher-key-badge"' in teacher_html
    assert "Option B" in teacher_html


def test_supplementary_builder_answer_key_rubric_and_omr_sheet() -> None:
    """Verify Separate Answer Key, Point-wise Marking Scheme, and Candidate/OMR Sheet generation."""
    project = _build_comprehensive_project()

    key_html = SupplementaryBuilder.compile_answer_key_html(project)
    assert "OFFICIAL ANSWER KEY — Set A" in key_html
    assert "(B) Tesla" in key_html
    assert "SECRET_APPLIED_FORCE" in key_html

    rubric_html = SupplementaryBuilder.compile_marking_scheme_html(project)
    assert "MARKING SCHEME & EVALUATION RUBRIC — Set A" in rubric_html
    assert "Formula statement [2M]" in rubric_html
    assert "Award full marks if symbols are defined." in rubric_html

    omr_html = SupplementaryBuilder.compile_candidate_omr_sheet_html(project)
    assert "CANDIDATE RESPONSE & OMR SHEET" in omr_html
    assert "Candidate Name:" in omr_html


def test_headless_pdf_byte_and_file_generation(tmp_path: Path) -> None:
    """Verify headless vector PDF compilation produces valid multi-page `%PDF` files for paper and supplementary sheets."""
    project = _build_comprehensive_project()

    paper_pdf = PDFExporter.export_project_to_pdf(project, tmp_path / "exam_paper.pdf")
    key_pdf = PDFExporter.export_answer_key_pdf(project, tmp_path / "answer_key.pdf")
    rubric_pdf = PDFExporter.export_marking_scheme_pdf(project, tmp_path / "marking_scheme.pdf")
    omr_pdf = PDFExporter.export_candidate_sheet_pdf(project, tmp_path / "candidate_omr.pdf")

    for pdf_path in (paper_pdf, key_pdf, rubric_pdf, omr_pdf):
        assert pdf_path.exists()
        raw = pdf_path.read_bytes()
        assert raw.startswith(b"%PDF-"), f"Invalid PDF header in {pdf_path}"
        reader = PdfReader(str(pdf_path))
        assert len(reader.pages) >= 1
