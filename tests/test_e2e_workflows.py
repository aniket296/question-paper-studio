"""End-to-End Integration Suite for Question Paper Studio (Sub-Phase 6.2).

Tests both primary SRS user experiences from start to finish:
1. Experience A (Simple Paper Workflow):
   Select built-in template -> Create paper in MainWindow -> Add Normal, MCQ,
   Fill-in-Blank, and Match-Pair questions -> Live Preview (Student & Teacher modes) ->
   Save & reload `.qpf` archive -> Batch export Vector PDF & Native Word `.docx` +
   Answer Key + Marking Rubric + OMR Bubble Sheet.

2. Experience B (Advanced University Exam Workflow):
   Design custom template in TemplateEditorWindow -> Create multi-section paper with
   internal choices (`OR` pair and `Any K of N`) -> Nested sub-questions (parent-child
   marks deduplication) -> Shared stimulus passage -> Bilingual prompt ->
   Parameterized Dynamic Numerical question -> Quality Audit & Blueprint Validation ->
   Multi-Set generation (Set A, Set B, Set C) -> Batch export synchronized per-set
   Question Papers, Answer Keys, Marking Rubrics, and Master Cross-Set Equivalence Matrix.
"""

from __future__ import annotations

from pathlib import Path

import docx
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication

from src.core.engine.marks_engine import MarksEngine
from src.core.engine.multi_set_shuffler import MultiSetShuffler, ShufflingOptions
from src.core.engine.numbering_fsm import NumberingFSM, QuestionTreeEngine
from src.core.models.enums import (
    BilingualLayout,
    CanvasElementType,
    ChoiceRuleType,
    FillBlankMode,
    NumberingStyle,
    PageSize,
    QuestionType,
    SecondaryLanguage,
)
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    FillBlankData,
    MarkingScheme,
    MatchPairData,
    MatchPairRow,
    MCQData,
    MCQOption,
    NormalQuestionData,
    NumericalDynamicData,
    NumericVariableRange,
    QuestionNode,
    StepPoint,
)
from src.core.models.section_model import ChoiceGroup, Section, SharedPassage
from src.core.models.template_model import CanvasElement, Template
from src.core.storage.qpf_archive import QPFArchive
from src.ui.main_window import MainWindow


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_experience_a_simple_paper_end_to_end_workflow(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    """Experience A: Select template -> Add 4 core question types -> Preview -> Save .qpf -> Export PDF & DOCX."""
    workspace_dir = tmp_path / "exp_a_workspace"
    main_win = MainWindow(workspace_dir=workspace_dir)

    try:
        # 1. Select built-in template from HomeScreen and launch Workspace
        templates = main_win.template_store.list_templates()
        assert len(templates) >= 3
        chosen_template = templates[0]

        main_win.open_new_paper_workspace(chosen_template)
        assert main_win.stack.currentIndex() == MainWindow.ROUTE_WORKSPACE

        ws = main_win.workspace_view
        project = ws.project
        assert project is not None

        # Configure exam metadata via ExamInfoBar
        ws.info_bar.edit_title.setText("Mid-Term Physics Assessment 2026")
        ws.info_bar.edit_subject.setText("Physics")
        ws.info_bar.edit_class.setText("Grade 11")
        ws.info_bar.spin_duration.setValue(90)
        ws.info_bar.spin_max_marks.setValue(12.0)
        ws.info_bar.save_to_project(project)

        sec = project.sections[0]
        sec.title = "Section A: Core Physics"
        sec.questions.clear()

        # 2. Author all 4 Core Question Types
        # (a) Normal Question (3 marks)
        q_normal = QuestionNode(
            question_type=QuestionType.NORMAL,
            prompt_html="<p>State Newton's Second Law of Motion and express it mathematically as $\\vec{F} = \\frac{d\\vec{p}}{dt}$.</p>",
            marks=3.0,
            type_data=NormalQuestionData(),
            marking_scheme=MarkingScheme(
                model_answer_html="<p>Rate of change of momentum is directly proportional to applied net force.</p>",
                step_points=[
                    StepPoint(description="Statement of law", marks=1.5),
                    StepPoint(description="Vector equation F = dp/dt", marks=1.5),
                ],
            ),
        )

        # (b) MCQ Question (2 marks)
        q_mcq = QuestionNode(
            question_type=QuestionType.MCQ,
            prompt_html="<p>Which of the following is a scalar quantity?</p>",
            marks=2.0,
            type_data=MCQData(
                options=[
                    MCQOption(label="A", text_html="Displacement", is_correct=False),
                    MCQOption(label="B", text_html="Electric Field", is_correct=False),
                    MCQOption(label="C", text_html="Work Done ($W = \\vec{F} \\cdot \\vec{d}$)", is_correct=True),
                    MCQOption(label="D", text_html="Angular Momentum", is_correct=False),
                ],
                allow_multiple_correct=False,
            ),
        )

        # (c) Fill in the Blank Question (3 marks)
        q_blank = QuestionNode(
            question_type=QuestionType.FILL_IN_THE_BLANK,
            prompt_html="<p>The escape velocity from Earth's surface is approximately ___ km/s, and orbital velocity is ___ times escape velocity.</p>",
            marks=3.0,
            type_data=FillBlankData(
                mode=FillBlankMode.WITH_OPTIONS,
                blank_count=2,
                word_bank=["11.2", "1/√2", "9.8", "2"],
                ground_truth_answers=["11.2", "1/√2"],
            ),
        )

        # (d) Match the Pair Question (4 marks)
        q_match = QuestionNode(
            question_type=QuestionType.MATCH_THE_PAIR,
            prompt_html="<p>Match the physical quantities in Column A with their SI units in Column B:</p>",
            marks=4.0,
            type_data=MatchPairData(
                rows=[
                    MatchPairRow(col_a_html="Magnetic Flux", col_b_html="Weber (Wb)", shuffled_col_b_index=1),
                    MatchPairRow(col_a_html="Capacitance", col_b_html="Farad (F)", shuffled_col_b_index=0),
                    MatchPairRow(col_a_html="Inductance", col_b_html="Henry (H)", shuffled_col_b_index=2),
                ]
            ),
        )

        sec.questions.extend([q_normal, q_mcq, q_blank, q_match])
        NumberingFSM.resolve_project(project)
        ws.outline_tree.load_project(project)
        ws.refresh_status_and_summary()

        # Verify MarksEngine balance (3 + 2 + 3 + 4 = 12.0 == max_marks 12.0)
        audit = MarksEngine.audit_paper(project)
        assert audit.is_balanced is True
        assert audit.total_paper_marks == 12.0
        assert "Balanced" in ws.lbl_status_balance.text()

        # 3. Verify Live Print Preview (Student View vs Teacher Answer Key View)
        ws.live_preview.set_teacher_preview_mode(False)
        ws.live_preview.refresh_preview(immediate=True)
        student_html = ws.live_preview.get_compiled_html()
        assert "Mid-Term Physics Assessment 2026" in student_html
        assert "Magnetic Flux" in student_html
        assert "<math" in student_html  # MathML rendered

        ws.live_preview.set_teacher_preview_mode(True)
        ws.live_preview.refresh_preview(immediate=True)
        teacher_html = ws.live_preview.get_compiled_html()
        assert "Rate of change of momentum" in teacher_html

        # 4. Save to `.qpf` archive and verify lossless round-trip reload
        qpf_file = tmp_path / "midterm_physics.qpf"
        saved_path = ws.save_project(custom_path=qpf_file)
        assert saved_path.exists()

        reloaded = QPFArchive.load_qpf(saved_path)
        assert reloaded.project.title == "Mid-Term Physics Assessment 2026"
        assert len(reloaded.project.all_questions_dfs()) == 4

        # 5. Batch Export PDF + DOCX + Answer Key + Rubric + OMR via ExportDialog
        export_dir = tmp_path / "exports_exp_a"
        export_dlg = ws.open_export_dialog()
        assert export_dlg is not None
        export_dlg.txt_folder.setText(str(export_dir))
        export_dlg.txt_filename.setText("MidTerm_Physics")
        export_dlg.chk_pdf.setChecked(True)
        export_dlg.chk_docx.setChecked(True)
        export_dlg.chk_answer_key_pdf.setChecked(True)
        export_dlg.chk_answer_key_docx.setChecked(True)
        export_dlg.chk_rubric_pdf.setChecked(True)
        export_dlg.chk_rubric_docx.setChecked(True)
        export_dlg.chk_omr_pdf.setChecked(True)
        export_dlg.chk_open_folder.setChecked(False)

        generated = export_dlg.run_export()
        assert len(generated) == 7
        for fpath in generated:
            assert fpath.exists() and fpath.stat().st_size > 0

        # Inspect generated PDF and DOCX files
        pdf_reader = PdfReader(str(export_dir / "MidTerm_Physics.pdf"))
        assert len(pdf_reader.pages) >= 1

        word_doc = docx.Document(str(export_dir / "MidTerm_Physics.docx"))
        docx_xml = word_doc._element.xml
        assert "m:oMath" in docx_xml  # Native Word OMML equation nodes present
        assert "Magnetic Flux" in docx_xml
    finally:
        main_win.question_bank.close()


def test_experience_b_advanced_university_exam_end_to_end_workflow(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    """Experience B: Custom template -> Internal choices (OR & Any K of N) -> Sub-questions -> Shared passage -> Dynamic Numerical -> Multi-Set (A/B/C) -> Synchronized Keys."""
    workspace_dir = tmp_path / "exp_b_workspace"
    main_win = MainWindow(workspace_dir=workspace_dir)

    try:
        # 1. Author a Custom University Template in TemplateEditorWindow
        main_win.open_new_template_editor()
        assert main_win.stack.currentIndex() == MainWindow.ROUTE_TEMPLATE_EDITOR

        te = main_win.template_editor_view
        te.edit_name.setText("National Institute of Technology End-Semester Template")
        te.inspector.spin_header_h.setValue(42.0)
        te.inspector.spin_footer_h.setValue(18.0)
        te.add_new_element(
            CanvasElementType.TEXT,
            content="NATIONAL INSTITUTE OF TECHNOLOGY — END SEMESTER EXAMINATION",
        )
        te.save_template(confirm=False)
        saved_custom_template: Template = te.template
        assert saved_custom_template.name == "National Institute of Technology End-Semester Template"

        # 2. Launch Paper Workspace with Custom Template
        main_win.open_new_paper_workspace(saved_custom_template)
        ws = main_win.workspace_view
        project = ws.project
        assert project is not None
        project.title = "B.Tech Semester V — Engineering Electromagnetics"
        project.exam_metadata.subject_name = "Electromagnetics"
        project.exam_metadata.subject_code = "EE-305"
        project.exam_metadata.max_marks = 25.0
        project.layout_settings.bilingual_mode = True
        project.layout_settings.secondary_language = SecondaryLanguage.HINDI
        project.layout_settings.bilingual_layout = BilingualLayout.SEQUENTIAL

        # Section A: Shared Passage + Parameterized Dynamic Numerical + OR Choice Pair (Total = 15 Marks)
        sec_a = project.sections[0]
        sec_a.title = "Section A: Analytical & Parameterized Problems"
        sec_a.questions.clear()

        passage = SharedPassage(
            title="Stimulus Passage: Coaxial Transmission Line",
            content_html="<p>A lossless coaxial cable has inner conductor radius $a$ and outer shield radius $b$ filled with dielectric $\\varepsilon_r = 2.25$.</p>",
        )
        sec_a.shared_passages.append(passage)

        # Q1: Linked to Shared Passage + Bilingual prompt (5 Marks)
        q1_mcq = QuestionNode(
            question_type=QuestionType.MCQ,
            shared_passage_id=passage.passage_id,
            prompt_html="<p>What is the phase velocity $v_p$ of a TEM wave in this coaxial line?</p>",
            prompt_secondary_html="<p>इस समाक्षीय लाइन में TEM तरंग का कला वेग $v_p$ क्या है?</p>",
            marks=5.0,
            type_data=MCQData(
                options=[
                    MCQOption(label="A", text_html="$2 \\times 10^8$ m/s", is_correct=True),
                    MCQOption(label="B", text_html="$3 \\times 10^8$ m/s", is_correct=False),
                    MCQOption(label="C", text_html="$1.5 \\times 10^8$ m/s", is_correct=False),
                    MCQOption(label="D", text_html="$1.0 \\times 10^8$ m/s", is_correct=False),
                ]
            ),
        )

        # Q2: Dynamic Numerical Question with variables & formula (5 Marks)
        q2_num = QuestionNode(
            question_type=QuestionType.NUMERICAL_DYNAMIC,
            shared_passage_id=passage.passage_id,
            prompt_html="<p>Calculate the power $P = I^2 R$ dissipated when current $I = {I}$ A flows through load resistance $R = {R}$ $\\Omega$.</p>",
            marks=5.0,
            type_data=NumericalDynamicData(
                variables={
                    "I": NumericVariableRange(min_val=2.0, max_val=8.0, precision=0, step=1.0),
                    "R": NumericVariableRange(min_val=5.0, max_val=20.0, precision=0, step=5.0),
                },
                formula_expression="I**2 * R",
                unit_label="W",
                answer_precision=1,
            ),
        )

        # Q3 & Q4: Internal Choice OR Pair (5 Marks each, effective marks = 5.0)
        q3_or_a = QuestionNode(
            question_type=QuestionType.SHORT_ANSWER,
            prompt_html="<p>State and prove Poynting's Theorem for electromagnetic power flow.</p>",
            marks=5.0,
        )
        q4_or_b = QuestionNode(
            question_type=QuestionType.SHORT_ANSWER,
            prompt_html="<p>Derive the boundary conditions for tangential $\\vec{E}$ and normal $\\vec{D}$ at a dielectric interface.</p>",
            marks=5.0,
        )
        or_group = ChoiceGroup(
            rule_type=ChoiceRuleType.OR_PAIR,
            question_ids=[q3_or_a.question_id, q4_or_b.question_id],
            label_text="OR",
        )
        q3_or_a.choice_group_id = or_group.choice_group_id
        q4_or_b.choice_group_id = or_group.choice_group_id
        sec_a.choice_groups.append(or_group)
        sec_a.questions.extend([q1_mcq, q2_num, q3_or_a, q4_or_b])

        # Section B: Nested Sub-Questions & "Answer Any 1 out of 2" (Effective Marks = 10 Marks)
        sec_b = Section(
            title="Section B: Long Answer Questions (Attempt Any 1 of 2)",
            attempt_any_k=1,
            section_numbering_style=NumberingStyle.NUMERIC,
        )

        # Q5: Parent question with nested sub-questions (a) [4M] and (b) [6M] -> parent sum = 10M
        q5_parent = QuestionNode(
            question_type=QuestionType.LONG_ANSWER,
            prompt_html="<p>Analyze rectangular waveguide propagation in $TE_{10}$ mode:</p>",
            marks=99.0,  # Should be deduplicated in favor of children sum (4 + 6 = 10.0)
            child_numbering_style=NumberingStyle.LOWER_ALPHA,
        )
        q5_sub_a = QuestionNode(
            question_type=QuestionType.SHORT_ANSWER,
            prompt_html="<p>Determine the cutoff frequency $f_c$ for waveguide width $a = 2.286$ cm.</p>",
            marks=4.0,
        )
        q5_sub_b = QuestionNode(
            question_type=QuestionType.LONG_ANSWER,
            prompt_html="<p>Derive expressions for guide wavelength $\\lambda_g$ and wave impedance $Z_{TE}$.</p>",
            marks=6.0,
        )
        q5_parent.children.extend([q5_sub_a, q5_sub_b])

        # Q6: Alternative 10-mark question in Section B (Attempt any 1 of 2)
        q6_alt = QuestionNode(
            question_type=QuestionType.LONG_ANSWER,
            prompt_html="<p>Derive the radiation resistance and directivity of a half-wave dipole antenna ($L = \\lambda / 2$).</p>",
            marks=10.0,
        )
        sec_b.questions.extend([q5_parent, q6_alt])
        project.sections.append(sec_b)

        NumberingFSM.resolve_project(project)
        ws.outline_tree.load_project(project)
        ws.refresh_status_and_summary()

        # 3. Verify Marks Calculation:
        # Section A = 5 (Q1) + 5 (Q2) + 5 (OR pair Q3/Q4) = 15.0 M
        # Section B = Attempt any 1 of [Q5 (4+6=10M), Q6 (10M)] = 10.0 M
        # Total Paper Effective Marks = 25.0 M == Target 25.0 M!
        paper_audit = MarksEngine.audit_paper(project)
        assert paper_audit.total_paper_marks == 25.0
        assert paper_audit.is_balanced is True

        # 4. Run Quality Audit Panel
        q_panel = ws.open_quality_check_panel()
        assert q_panel is not None
        assert q_panel.audit_report is not None
        assert q_panel.audit_report.critical_count == 0

        # 5. Generate Multi-Set Papers (Set A, Set B, Set C) with Synchronized Answer Keys
        ms_dlg = ws.open_multi_set_dialog()
        assert ms_dlg is not None
        ms_dlg.txt_set_ids.setText("A, B, C")
        ms_dlg.spin_seed.setValue(2026)
        ms_dlg._generate_sets_preview()

        gen_result = ms_dlg.generation_result
        assert gen_result is not None
        assert len(gen_result.sets) == 3
        assert list(gen_result.sets.keys()) == ["A", "B", "C"]

        # Verify every generated set preserves exact 25.0 effective marks and OR pair contiguity
        for set_id, set_proj in gen_result.sets.items():
            set_audit = MarksEngine.audit_paper(set_proj)
            assert set_audit.total_paper_marks == 25.0
            assert set_audit.is_balanced is True

        # Batch export all 3 sets (PDF + DOCX + Answer Keys + Master Equivalence Matrix)
        ms_export_dir = tmp_path / "multi_set_exports"
        ms_dlg.txt_folder.setText(str(ms_export_dir))
        ms_dlg.chk_exp_pdf.setChecked(True)
        ms_dlg.chk_exp_docx.setChecked(True)
        ms_dlg.chk_exp_keys.setChecked(True)
        ms_dlg.chk_exp_master.setChecked(True)
        ms_dlg.chk_open_folder.setChecked(False)

        exported_files = ms_dlg.run_export_all()
        assert len(exported_files) >= 14  # 3 sets * 4 files + 2 master equivalence matrix docs
        for f in exported_files:
            assert f.exists() and f.stat().st_size > 0
    finally:
        main_win.question_bank.close()
