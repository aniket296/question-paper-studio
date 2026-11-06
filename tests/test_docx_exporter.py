"""Unit tests for Sub-phase 2.3: Native Editable DOCX Exporter with OMML Math Equations."""

from __future__ import annotations

import zipfile
from pathlib import Path

import docx
from lxml import etree
from PIL import Image

from src.core.models import (
    CandidateFieldType,
    DiagramAttachment,
    ExamMetadata,
    MCQData,
    MarkingScheme,
    MatchPairData,
    ProjectState,
    QuestionNode,
    QuestionType,
    Section,
    StepPoint,
)
from src.core.storage import TemplateStore
from src.rendering import (
    DOCXExporter,
    MathConverter,
    OMML_NS,
    WORD_NS,
)


def test_math_converter_latex_to_mathml_and_native_omml() -> None:
    """Verify LaTeX converts to MathML and native Word `<m:oMath>` (`<m:f>`, `<m:rad>`, `<m:sSup>`, `<m:sSub>`)."""
    expr = r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a} + x_i^n"

    mml = MathConverter.latex_to_mathml(expr)
    assert "<math" in mml
    assert "<mfrac>" in mml
    assert "<msqrt>" in mml

    omml_el = MathConverter.latex_to_omml_element(expr, display_block=False)
    xml_str = etree.tostring(omml_el, encoding="unicode")

    assert "oMath" in xml_str
    assert f"{{{OMML_NS}}}f" in [e.tag for e in omml_el.iter()]      # Fraction <m:f>
    assert f"{{{OMML_NS}}}rad" in [e.tag for e in omml_el.iter()]    # Radical <m:rad>
    assert f"{{{OMML_NS}}}sSup" in [e.tag for e in omml_el.iter()]   # Superscript <m:sSup>


def test_docx_exporter_openxml_structure_omml_headers_and_supplementary_docs(tmp_path: Path) -> None:
    """Verify `.docx` compilation produces valid OpenXML with `<m:oMath>`, `PAGE`/`NUMPAGES` fields, tables, and embedded images."""
    diag_file = tmp_path / "optics_ray.png"
    Image.new("RGB", (200, 120), color=(37, 99, 235)).save(diag_file)

    store = TemplateStore(storage_dir=tmp_path / "templates")
    tmpl = store.get_template("builtin-standard-school-a4")
    assert tmpl is not None
    project = ProjectState.create_from_template(tmpl, title="Engineering Mathematics I")
    project.exam_metadata = ExamMetadata(
        exam_name="END SEMESTER EXAMINATION",
        subject_name="Engineering Mathematics I",
        subject_code="MA-101",
        class_semester="B.Tech Sem I",
        duration_minutes=180,
        max_marks=100.0,
        set_identifier="Set A",
        general_instructions=r"<p>Attempt all sections. Use $\pi = 3.14159$ where required.</p>",
        candidate_fields=[CandidateFieldType.STUDENT_NAME, CandidateFieldType.ROLL_NO],
    )

    sec = Section(
        title="Section A",
        instructions_html="<p>Solve the following problems.</p>",
        is_default_unsectioned=False,
    )

    # 1. Normal Question with LaTeX equation and attached diagram
    q1 = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html=r"<p>Evaluate the quadratic roots using $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$ and sketch the ray diagram.</p>",
        marks=5.0,
        answer_space_lines=2,
        diagrams=[
            DiagramAttachment(
                asset_path=str(diag_file),
                width_mm=65.0,
                height_mm=40.0,
                caption="Figure 1: Ray Path",
            )
        ],
        marking_scheme=MarkingScheme(
            model_answer_html=r"<p>Discriminant $\Delta = b^2 - 4ac$</p>",
            step_points=[StepPoint(description="Discriminant", marks=2.0), StepPoint(description="Roots", marks=3.0)],
        ),
    )
    sec.add_question(q1)

    # 2. MCQ Question (rendered in borderless 2x2 table)
    mcq = MCQData()
    mcq.options[0].text_html = r"$\sin(x)$"
    mcq.add_option(r"$\cos(x)$", is_correct=True)
    mcq.add_option(r"$-\sin(x)$", is_correct=False)
    mcq.add_option(r"$\tan(x)$", is_correct=False)
    q2 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html=r"<p>What is the derivative $\frac{d}{dx}\sin(x)$?</p>",
        marks=2.0,
        type_data=mcq,
    )
    sec.add_question(q2)

    # 3. Match the Pair Question (rendered in bordered 2-column table)
    mp = MatchPairData()
    mp.rows[0].col_a_html = r"$\int x dx$"
    mp.rows[0].col_b_html = r"$\frac{x^2}{2} + C$"
    mp.rows[1].col_a_html = r"$\int \frac{1}{x} dx$"
    mp.rows[1].col_b_html = r"$\ln|x| + C$"
    q3 = QuestionNode(
        question_type=QuestionType.MATCH_THE_PAIR,
        prompt_html="<p>Match the integrals with their antiderivatives:</p>",
        marks=4.0,
        type_data=mp,
    )
    sec.add_question(q3)

    project.sections = [sec]

    paper_docx = DOCXExporter.export_project_to_docx(project, tmp_path / "math_paper.docx")
    key_docx = DOCXExporter.export_answer_key_docx(project, tmp_path / "math_key.docx")
    rubric_docx = DOCXExporter.export_marking_scheme_docx(project, tmp_path / "math_rubric.docx")

    for dpath in (paper_docx, key_docx, rubric_docx):
        assert dpath.exists()
        assert zipfile.is_zipfile(dpath)

    # Open with python-docx and verify page geometry, headers, and tables
    loaded_doc = docx.Document(str(paper_docx))
    w_sec = loaded_doc.sections[0]
    assert round(w_sec.page_width.mm, 1) == 210.0
    assert round(w_sec.page_height.mm, 1) == 297.0
    assert w_sec.different_first_page_header_footer is True

    hdr_text = "\n".join(p.text for p in w_sec.first_page_header.paragraphs)
    assert "END SEMESTER EXAMINATION" in hdr_text
    assert "Engineering Mathematics I" in hdr_text

    # Inspect raw OpenXML inside `word/document.xml` and `word/footer*.xml`
    with zipfile.ZipFile(paper_docx, "r") as zf:
        doc_xml_bytes = zf.read("word/document.xml")
        doc_root = etree.fromstring(doc_xml_bytes)

        # Verify native `<m:oMath>` tags exist inside `word/document.xml`
        omath_nodes = doc_root.findall(f".//{{{OMML_NS}}}oMath")
        assert len(omath_nodes) >= 6

        # Verify `keepNext` / `keepLines` and right tab stops exist
        keep_lines = doc_root.findall(f".//{{{WORD_NS}}}keepLines")
        assert len(keep_lines) >= 3
        tabs = doc_root.findall(f".//{{{WORD_NS}}}tab")
        assert len(tabs) >= 3

        # Verify native Word `PAGE` and `NUMPAGES` fields exist in footer XMLs
        footer_xmls = [
            zf.read(name).decode("utf-8")
            for name in zf.namelist()
            if name.startswith("word/footer") and name.endswith(".xml")
        ]
        combined_footers = "\n".join(footer_xmls)
        assert "PAGE" in combined_footers
        assert "NUMPAGES" in combined_footers
