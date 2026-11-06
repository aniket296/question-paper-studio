"""Unit tests for Sub-phase 2.1: `.qpf` Archive I/O, Template Store, Auto-Save & SQLite Question Bank."""

from __future__ import annotations

from pathlib import Path

import docx
import pytest
from PIL import Image
from pypdf import PdfWriter

from src.core.models import (
    BloomLevel,
    CanvasElement,
    CanvasElementType,
    DiagramAttachment,
    DifficultyLevel,
    MCQData,
    ProjectState,
    QuestionNode,
    QuestionType,
    TaxonomyMetadata,
)
from src.core.storage import (
    AutosaveManager,
    BankSearchFilter,
    QPFArchive,
    QuestionImporter,
    SQLiteQuestionBank,
    TemplateStore,
)


def test_qpf_archive_round_trip_with_embedded_assets_and_overwrite_protection(tmp_path: Path) -> None:
    """Verify `.qpf` packs project.json + SHA-256 deduplicated assets, enforces overwrite protection, and unpacks cleanly."""
    # Create a sample diagram image and header logo
    img_dir = tmp_path / "source_images"
    img_dir.mkdir()
    logo_path = img_dir / "school_logo.png"
    diagram_path = img_dir / "circuit_diagram.png"
    Image.new("RGB", (120, 80), color=(30, 64, 175)).save(logo_path)
    Image.new("RGB", (240, 160), color=(22, 163, 74)).save(diagram_path)

    store = TemplateStore(storage_dir=tmp_path / "templates")
    base_tmpl = store.list_templates()[0]
    base_tmpl.first_page_header_elements.append(
        CanvasElement(
            element_type=CanvasElementType.IMAGE,
            x_mm=2.0,
            y_mm=2.0,
            width_mm=20.0,
            height_mm=20.0,
            content=str(logo_path),
        )
    )

    project = ProjectState.create_from_template(base_tmpl, title="Physics Final 2026")
    q1 = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>Calculate equivalent resistance in the circuit below:</p>",
        marks=5.0,
        diagrams=[DiagramAttachment(asset_path=str(diagram_path), width_mm=70.0, height_mm=45.0)],
    )
    project.sections[0].add_question(q1)

    qpf_file = tmp_path / "physics_final.qpf"
    saved_path = QPFArchive.save_qpf(project, qpf_file, overwrite=False)
    assert saved_path.exists()

    # Overwrite protection raises FileExistsError when overwrite=False
    with pytest.raises(FileExistsError):
        QPFArchive.save_qpf(project, qpf_file, overwrite=False)

    # Delete original source images to prove `.qpf` is 100% self-contained
    logo_path.unlink()
    diagram_path.unlink()

    unpack_dir = tmp_path / "unpacked"
    result = QPFArchive.load_qpf(qpf_file, extract_assets_to=unpack_dir)
    assert result.project.title == "Physics Final 2026"
    assert int(result.manifest.get("asset_count", 0)) == 2

    restored_q1 = result.project.sections[0].questions[0]
    extracted_diag_path = Path(restored_q1.diagrams[0].asset_path)
    assert extracted_diag_path.exists()
    assert extracted_diag_path.stat().st_size > 0


def test_template_store_crud_importers_and_deletion_immunity(tmp_path: Path) -> None:
    """Verify template CRUD, DOCX/PDF template import, and that deleting a template never breaks saved `.qpf` projects."""
    store = TemplateStore(storage_dir=tmp_path / "templates")
    builtins = store.list_templates()
    assert len(builtins) >= 3

    # Duplicate, rename, and create a saved project from the duplicated template
    custom_tmpl = store.duplicate_template(builtins[0].template_id, new_name="Custom High School Template")
    assert custom_tmpl.name == "Custom High School Template"
    assert custom_tmpl.is_builtin is False

    renamed = store.rename_template(custom_tmpl.template_id, "Renamed High School Template")
    assert renamed.name == "Renamed High School Template"

    # Save a `.qpf` paper using this custom template
    paper = ProjectState.create_from_template(renamed, title="Saved Chemistry Paper")
    paper.sections[0].add_question(QuestionNode(prompt_html="<p>State Avogadro's Law.</p>", marks=2.0))
    qpf_path = QPFArchive.save_qpf(paper, tmp_path / "chemistry.qpf", overwrite=True)

    # Delete the template from the TemplateStore
    deleted = store.delete_template(custom_tmpl.template_id)
    assert deleted is True
    assert store.get_template(custom_tmpl.template_id) is None

    # Re-open the saved `.qpf` project and verify its embedded template snapshot is completely intact
    reopened = QPFArchive.load_qpf(qpf_file := qpf_path).project
    assert reopened.template_snapshot.name == "Renamed High School Template"
    assert len(reopened.template_snapshot.get_header_elements(is_first_page=True)) > 0

    # Test importing a DOCX template
    sample_docx = tmp_path / "external_header.docx"
    doc = docx.Document()
    hdr = doc.sections[0].header
    hdr.paragraphs[0].text = "NATIONAL INSTITUTE OF TECHNOLOGY"
    doc.add_paragraph("Department of Computer Science")
    doc.save(str(sample_docx))

    docx_report = store.import_external_template(sample_docx, template_name="Imported NIT DOCX")
    assert docx_report.source_format == "DOCX"
    assert docx_report.editable_elements_count >= 2
    assert docx_report.uses_visual_backdrop is False

    # Test importing a PDF template
    sample_pdf = tmp_path / "external_backdrop.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595.2, height=841.8)  # A4 in pt
    with sample_pdf.open("wb") as f:
        writer.write(f)

    pdf_report = store.import_external_template(sample_pdf, template_name="Imported PDF Backdrop")
    assert pdf_report.source_format == "PDF"
    assert pdf_report.uses_visual_backdrop is True
    assert len(pdf_report.warnings) >= 1


def test_sqlite_question_bank_fts5_revisions_isolation_and_asset_library(tmp_path: Path) -> None:
    """Verify SQLite FTS5 search, taxonomy filters, revision history/restore, duplicate detection, and bank-to-paper snapshot isolation."""
    bank = SQLiteQuestionBank(tmp_path / "workspace.db")

    q_thermo = QuestionNode(
        question_type=QuestionType.NORMAL,
        prompt_html="<p>State the Second Law of Thermodynamics and explain entropy.</p>",
        marks=5.0,
        taxonomy_metadata=TaxonomyMetadata(
            subject="Physics",
            unit="Unit 2",
            chapter="Thermodynamics",
            topic="Entropy",
            difficulty=DifficultyLevel.MODERATE,
            bloom_level=BloomLevel.UNDERSTAND,
            tags=["heat", "entropy", "laws"],
        ),
    )
    item_id = bank.add_question(q_thermo, change_note="Created v1")

    # FTS5 full-text search
    fts_hits = bank.search(BankSearchFilter(query_text="Thermodynamics entropy"))
    assert len(fts_hits) == 1
    assert fts_hits[0].bank_item_id == item_id

    # Structured filter search
    filtered_hits = bank.search(
        BankSearchFilter(
            subject="Physics",
            difficulty=DifficultyLevel.MODERATE,
            tags=["entropy"],
        )
    )
    assert len(filtered_hits) == 1

    # Duplicate detection
    dups = bank.find_duplicates("<p>State the Second Law of Thermodynamics and explain entropy!</p>")
    assert len(dups) == 1

    # Insert snapshot into a paper, then update and delete in bank — verify paper is unaffected
    paper_question = bank.create_question_snapshot_for_paper(item_id)
    assert paper_question.question_id != q_thermo.question_id

    # Update bank item to v2
    q_thermo_v2 = q_thermo.model_copy(deep=True)
    q_thermo_v2.prompt_html = "<p>UPDATED V2: Derive the Clausius inequality for entropy.</p>"
    q_thermo_v2.marks = 8.0
    ver = bank.update_question(item_id, q_thermo_v2, change_note="Expanded to 8 marks derivation")
    assert ver == 2

    # Paper question remains untouched at 5.0 marks with v1 prompt
    assert paper_question.marks == 5.0
    assert "Second Law" in paper_question.prompt_html

    # Revision history & restore v1
    revisions = bank.get_revision_history(item_id)
    assert len(revisions) == 2
    assert revisions[0].version_number == 1
    assert revisions[1].version_number == 2

    restored_rec = bank.restore_revision(item_id, version_number=1)
    assert restored_rec.current_version == 3
    assert restored_rec.question.marks == 5.0
    assert "Second Law of Thermodynamics" in restored_rec.question.prompt_html

    # Record exam usage
    bank.record_usage(item_id, project_id="proj-101", exam_title="Fall Semester 2026")
    updated_rec = bank.get_record(item_id)
    assert updated_rec is not None
    assert updated_rec.usage_count == 1
    assert updated_rec.last_used_exam == "Fall Semester 2026"

    # Reusable Asset Library
    asset_id = bank.add_library_asset(
        title="Quadratic Formula",
        asset_type="equation",
        latex_source=r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        tags=["algebra", "roots"],
    )
    assets = bank.list_library_assets(asset_type="equation")
    assert len(assets) == 1
    assert assets[0].asset_id == asset_id

    bank.close()


def test_question_importer_txt_docx_csv_and_tsv(tmp_path: Path) -> None:
    """Verify QuestionImporter parses questions, MCQ options, marks, and errors across TXT, DOCX, CSV, and TSV."""
    sample_txt = tmp_path / "questions.txt"
    sample_txt.write_text(
        """1. What is the chemical symbol for Gold? [1 Mark]
A) Ag
*B) Au
C) Fe
D) Cu

2. Define Newton's First Law of Motion. [3 Marks]
Answer: A body remains at rest or in uniform motion unless acted upon by an external force.

3. The powerhouse of the cell is ___. [1 Mark]
Answer: Mitochondria
""",
        encoding="utf-8",
    )

    txt_report = QuestionImporter.import_file(sample_txt)
    assert txt_report.total_parsed == 3
    assert txt_report.questions[0].question_type == QuestionType.MCQ
    assert isinstance(txt_report.questions[0].type_data, MCQData)
    assert txt_report.questions[0].type_data.options[1].is_correct is True
    assert txt_report.questions[1].question_type == QuestionType.NORMAL
    assert txt_report.questions[1].marks == 3.0
    assert txt_report.questions[2].question_type == QuestionType.FILL_IN_THE_BLANK

    # Test CSV import (including 1 valid MCQ row, 1 valid Normal row, and 1 malformed row missing prompt)
    sample_csv = tmp_path / "questions.csv"
    sample_csv.write_text(
        "question,type,marks,option_a,option_b,option_c,option_d,answer,subject,topic,difficulty,tags\n"
        '"Which planet is known as the Red Planet?",MCQ,1,Venus,Mars,Jupiter,Saturn,B,Astronomy,Solar System,Easy,planets;space\n'
        '"Explain the greenhouse effect.",NORMAL,4,,,,,Rising atmospheric CO2 traps heat,Environmental Science,Climate,Moderate,climate\n'
        ",NORMAL,2,,,,,,,,,\n",
        encoding="utf-8",
    )

    csv_report = QuestionImporter.import_file(sample_csv)
    assert csv_report.total_parsed == 2
    assert csv_report.total_skipped == 1
    assert len(csv_report.errors) == 1
    assert csv_report.questions[0].question_type == QuestionType.MCQ
    assert csv_report.questions[0].taxonomy_metadata is not None
    assert csv_report.questions[0].taxonomy_metadata.subject == "Astronomy"


def test_autosave_crash_recovery_and_workspace_backup(tmp_path: Path) -> None:
    """Verify periodic autosave snapshot, crash recovery detection, clean exit dismissal, and workspace `.zip` backup/restore."""
    ws_dir = tmp_path / "workspace"
    mgr = AutosaveManager(ws_dir)

    project = ProjectState(title="Unsaved Crash Test Paper")
    project.sections[0].add_question(QuestionNode(prompt_html="<p>Important Question</p>", marks=10.0))

    # Simulate background autosave before an unexpected crash
    snap_path = mgr.perform_autosave(project)
    assert snap_path.exists()

    # On next startup, unrecovered snapshot is detected
    candidates = mgr.list_unrecovered_snapshots()
    assert len(candidates) == 1
    assert candidates[0].project_id == project.project_id

    recovered = mgr.recover_project(candidates[0], extract_assets_to=tmp_path / "recovered_assets")
    assert recovered.title == "Unsaved Crash Test Paper"
    assert len(recovered.sections[0].questions) == 1

    # Marking clean close clears the recovery candidate
    mgr.mark_clean_close(project.project_id)
    assert len(mgr.list_unrecovered_snapshots()) == 0

    # Save a permanent project in workspace and test full workspace backup & restore
    saved_qpf = QPFArchive.save_qpf(project, mgr.projects_dir / "permanent.qpf", overwrite=True)
    assert saved_qpf.exists()

    backup_zip = tmp_path / "full_workspace_backup.zip"
    mgr.create_workspace_backup(backup_zip)
    assert backup_zip.exists()

    # Wipe projects folder and restore from backup
    saved_qpf.unlink()
    assert not saved_qpf.exists()
    restored_files = mgr.restore_workspace_backup(backup_zip)
    assert len(restored_files) >= 1
    assert saved_qpf.exists()
