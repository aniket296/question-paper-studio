"""Multi-Format Batch Export Dialog for Question Paper Studio.

Supports exporting:
- Question Paper (Vector PDF via QWebEngine / QPdfWriter)
- Question Paper (Editable Microsoft Word `.docx` with native OMML Math)
- Separate Answer Key & Solutions (`.pdf` / `.docx`)
- Step Breakdown & Marking Rubric (`.pdf` / `.docx`)
- Candidate Response / OMR Bubble Sheet (`.pdf`)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models.project_model import ProjectState
from src.rendering.docx_exporter import DOCXExporter
from src.rendering.pdf_exporter import PDFExporter


class ExportDialog(QDialog):
    """Modal dialog for multi-format document generation and batch exporting."""

    export_finished = Signal(list)  # List[Path]

    def __init__(
        self,
        project: ProjectState,
        default_dir: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: ProjectState = project
        self.exported_files: List[Path] = []

        # Determine default export directory
        if default_dir:
            self.export_dir: Path = Path(default_dir)
        else:
            self.export_dir = Path.home() / "Documents"
            if not self.export_dir.exists():
                self.export_dir = Path.cwd()

        self.setWindowTitle("Export Question Paper & Supplementary Materials")
        self.setMinimumWidth(560)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Dialog Header
        lbl_title = QLabel("📤 Export Documents")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0F172A;")
        layout.addWidget(lbl_title)

        lbl_sub = QLabel("Select formats and supplementary sheets to generate for this question paper.")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 9.5pt;")
        layout.addWidget(lbl_sub)

        # 2. Output Destination Group
        dest_group = QGroupBox("Destination & Naming")
        dest_lay = QVBoxLayout(dest_group)
        dest_lay.setSpacing(8)

        # Folder chooser row
        folder_lay = QHBoxLayout()
        folder_lbl = QLabel("Folder:")
        folder_lbl.setMinimumWidth(60)
        self.txt_folder = QLineEdit(str(self.export_dir))
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_folder)
        folder_lay.addWidget(folder_lbl)
        folder_lay.addWidget(self.txt_folder, 1)
        folder_lay.addWidget(self.btn_browse)
        dest_lay.addLayout(folder_lay)

        # Filename prefix row
        safe_prefix = "".join(
            c for c in self.project.title if c.isalnum() or c in ("-", "_", " ")
        ).strip().replace(" ", "_") or "Question_Paper"
        name_lay = QHBoxLayout()
        name_lbl = QLabel("Base Name:")
        name_lbl.setMinimumWidth(60)
        self.txt_filename = QLineEdit(safe_prefix)
        name_lay.addWidget(name_lbl)
        name_lay.addWidget(self.txt_filename, 1)
        dest_lay.addLayout(name_lay)

        layout.addWidget(dest_group)

        # 3. Question Paper Format Group
        qp_group = QGroupBox("Question Paper Document")
        qp_lay = QVBoxLayout(qp_group)
        qp_lay.setSpacing(6)

        # Vector PDF
        pdf_row = QHBoxLayout()
        self.chk_pdf = QCheckBox("Vector PDF Document (.pdf)")
        self.chk_pdf.setChecked(True)
        self.combo_pdf_mode = QComboBox()
        self.combo_pdf_mode.addItem("Student View (Clean Exam Paper)", False)
        self.combo_pdf_mode.addItem("Teacher Preview (With Answer Keys)", True)
        pdf_row.addWidget(self.chk_pdf)
        pdf_row.addSpacing(10)
        pdf_row.addWidget(self.combo_pdf_mode, 1)
        qp_lay.addLayout(pdf_row)

        # Word DOCX
        self.chk_docx = QCheckBox("Editable Microsoft Word Document (.docx) with Native Math equations")
        self.chk_docx.setChecked(True)
        qp_lay.addWidget(self.chk_docx)

        layout.addWidget(qp_group)

        # 4. Supplementary Sheets Group
        supp_group = QGroupBox("Supplementary Sheets & Keys")
        supp_lay = QVBoxLayout(supp_group)
        supp_lay.setSpacing(6)

        self.chk_answer_key_pdf = QCheckBox("Separate Answer Key — PDF (.pdf)")
        self.chk_answer_key_docx = QCheckBox("Separate Answer Key — Word (.docx)")
        self.chk_rubric_pdf = QCheckBox("Marking Scheme & Rubrics — PDF (.pdf)")
        self.chk_rubric_docx = QCheckBox("Marking Scheme & Rubrics — Word (.docx)")
        self.chk_omr_pdf = QCheckBox("Candidate Response / OMR Sheet — PDF (.pdf)")

        supp_lay.addWidget(self.chk_answer_key_pdf)
        supp_lay.addWidget(self.chk_answer_key_docx)
        supp_lay.addWidget(self.chk_rubric_pdf)
        supp_lay.addWidget(self.chk_rubric_docx)
        supp_lay.addWidget(self.chk_omr_pdf)

        layout.addWidget(supp_group)

        # 5. Options
        opt_lay = QHBoxLayout()
        self.chk_open_folder = QCheckBox("Open folder when export finishes")
        self.chk_open_folder.setChecked(True)
        self.chk_overwrite = QCheckBox("Overwrite existing files")
        self.chk_overwrite.setChecked(True)
        opt_lay.addWidget(self.chk_open_folder)
        opt_lay.addWidget(self.chk_overwrite)
        opt_lay.addStretch(1)
        layout.addLayout(opt_lay)

        # 6. Progress Bar and Status
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Ready to export.")
        self.lbl_status.setStyleSheet("color: #475569; font-size: 9pt;")
        layout.addWidget(self.lbl_status)

        # 7. Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)

        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("🚀 Start Export")
        self.btn_export.setObjectName("PrimaryButton")
        self.btn_export.setStyleSheet("""
            QPushButton#PrimaryButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 700;
                padding: 6px 16px;
                border-radius: 5px;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_export.clicked.connect(self.run_export)
        btn_box.addWidget(self.btn_export)

        layout.addLayout(btn_box)

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            self.txt_folder.text(),
        )
        if chosen:
            self.txt_folder.setText(chosen)

    # ========================================================================
    # Export Execution
    # ========================================================================

    def run_export(self) -> List[Path]:
        """Execute selected exports sequentially with progress updates."""
        target_dir = Path(self.txt_folder.text().strip())
        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.lbl_status.setText(f"Cannot create directory '{target_dir}': {e}")
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    QMessageBox.critical(self, "Export Error", f"Cannot create directory '{target_dir}':\n{e}")
                return []

        base_name = self.txt_filename.text().strip() or "Question_Paper"
        overwrite = self.chk_overwrite.isChecked()

        # Build task list: tuples of (description, callable)
        tasks = []

        if self.chk_pdf.isChecked():
            is_teacher = self.combo_pdf_mode.currentData()
            suffix = "_TeacherPreview.pdf" if is_teacher else ".pdf"
            p_path = target_dir / f"{base_name}{suffix}"
            tasks.append((
                "Question Paper PDF",
                lambda p=p_path, t=is_teacher: PDFExporter.export_project_to_pdf(
                    self.project,
                    p,
                    teacher_preview_mode=t,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_docx.isChecked():
            d_path = target_dir / f"{base_name}.docx"
            tasks.append((
                "Question Paper DOCX",
                lambda p=d_path: DOCXExporter.export_project_to_docx(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_answer_key_pdf.isChecked():
            ak_pdf = target_dir / f"{base_name}_AnswerKey.pdf"
            tasks.append((
                "Answer Key PDF",
                lambda p=ak_pdf: PDFExporter.export_answer_key_pdf(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_answer_key_docx.isChecked():
            ak_docx = target_dir / f"{base_name}_AnswerKey.docx"
            tasks.append((
                "Answer Key DOCX",
                lambda p=ak_docx: DOCXExporter.export_answer_key_docx(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_rubric_pdf.isChecked():
            ms_pdf = target_dir / f"{base_name}_MarkingScheme.pdf"
            tasks.append((
                "Marking Scheme PDF",
                lambda p=ms_pdf: PDFExporter.export_marking_scheme_pdf(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_rubric_docx.isChecked():
            ms_docx = target_dir / f"{base_name}_MarkingScheme.docx"
            tasks.append((
                "Marking Scheme DOCX",
                lambda p=ms_docx: DOCXExporter.export_marking_scheme_docx(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if self.chk_omr_pdf.isChecked():
            omr_pdf = target_dir / f"{base_name}_OMR_Sheet.pdf"
            tasks.append((
                "Candidate OMR Sheet PDF",
                lambda p=omr_pdf: PDFExporter.export_candidate_sheet_pdf(
                    self.project,
                    p,
                    overwrite=overwrite,
                ),
            ))

        if not tasks:
            self.lbl_status.setText("Please select at least one format or document to export.")
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.warning(self, "No Formats Selected", "Please select at least one format or document to export.")
            return []

        # UI state during export
        self.btn_export.setEnabled(False)
        self.progress_bar.setMaximum(len(tasks))
        self.progress_bar.setValue(0)
        self.exported_files.clear()

        errors = []
        for i, (desc, action) in enumerate(tasks, start=1):
            self.lbl_status.setText(f"Exporting {desc} ({i}/{len(tasks)})...")
            self.lbl_status.repaint()
            try:
                res_path = action()
                self.exported_files.append(res_path)
            except Exception as e:
                errors.append(f"{desc}: {e}")
            self.progress_bar.setValue(i)

        self.btn_export.setEnabled(True)

        if errors:
            err_msg = "\n".join(errors)
            self.lbl_status.setText(f"Completed with {len(errors)} error(s).")
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.warning(self, "Export Warnings", f"Some files could not be exported:\n{err_msg}")
        else:
            self.lbl_status.setText(f"✓ Successfully exported {len(self.exported_files)} file(s).")
            self.btn_cancel.setText("Done")

        self.export_finished.emit(self.exported_files)

        # Open folder if requested and not in headless test
        if self.chk_open_folder.isChecked() and not os.environ.get("PYTEST_CURRENT_TEST"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))

        return self.exported_files
