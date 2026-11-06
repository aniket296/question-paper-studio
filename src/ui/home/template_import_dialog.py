"""Template Import Dialog for importing `.docx`, `.pdf`, or `.qpt.json` templates with editable/backdrop preview."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models.template_model import Template
from src.core.storage.template_store import TemplateImportReport, TemplateStore


class TemplateImportDialog(QDialog):
    """Interactive dialog for importing external DOCX, PDF, or `.qpt` templates into the TemplateStore."""

    def __init__(
        self,
        template_store: TemplateStore,
        parent: Optional[QWidget] = None,
        initial_file_path: Optional[Path | str] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import External Template (DOCX / PDF / QPT)")
        self.resize(560, 400)
        self.template_store = template_store
        self.import_report: Optional[TemplateImportReport] = None
        self.imported_template: Optional[Template] = None

        self._build_ui()
        if initial_file_path is not None:
            self.set_source_file(Path(initial_file_path))

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        info_lbl = QLabel(
            "Select a Microsoft Word (.docx), PDF (.pdf), or native template (.qpt.json) file.\n"
            "The original source file is never modified."
        )
        info_lbl.setWordWrap(True)
        root_layout.addWidget(info_lbl)

        form = QFormLayout()
        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Choose a .docx, .pdf, or .qpt.json file...")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        file_row.addWidget(self.file_path_edit, 1)
        file_row.addWidget(self.browse_btn)
        form.addRow("Source File:", file_row)

        self.template_name_edit = QLineEdit()
        self.template_name_edit.setPlaceholderText("Enter a name for the imported template...")
        form.addRow("Template Name:", self.template_name_edit)
        root_layout.addLayout(form)

        self.analyze_btn = QPushButton("Analyze & Preview Import")
        self.analyze_btn.clicked.connect(self.run_import_preview)
        root_layout.addWidget(self.analyze_btn)

        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText(
            "Import analysis report (editable elements vs visual backdrop reference) will appear here..."
        )
        root_layout.addWidget(self.report_view, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("Import & Save Template")
        self.confirm_btn.setObjectName("PrimaryButton")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._on_confirm_clicked)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        root_layout.addLayout(btn_row)

    def set_source_file(self, file_path: Path) -> None:
        """Set the selected source file and auto-populate the template name."""
        self.file_path_edit.setText(str(file_path))
        if not self.template_name_edit.text().strip():
            self.template_name_edit.setText(file_path.stem.replace("_", " ").title())
        self.run_import_preview()

    def _on_browse_clicked(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Template File",
            "",
            "Template Files (*.docx *.pdf *.json *.qpt);;All Files (*.*)",
        )
        if chosen:
            self.set_source_file(Path(chosen))

    def run_import_preview(self) -> Optional[TemplateImportReport]:
        """Run the template importer and populate the editable vs visual backdrop analysis summary."""
        raw_path = self.file_path_edit.text().strip()
        if not raw_path:
            return None

        src_path = Path(raw_path)
        if not src_path.exists():
            QMessageBox.warning(self, "File Not Found", f"Source file does not exist:\n{src_path}")
            return None

        custom_name = self.template_name_edit.text().strip() or src_path.stem
        try:
            report = self.template_store.import_external_template(
                src_path,
                template_name=custom_name,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Template Import Error", str(exc))
            return None

        self.import_report = report
        self.imported_template = report.template

        lines = [
            f"Template Name      : {report.template.name}",
            f"Source Format      : {report.source_format}",
            f"Page Size & Orient : {report.template.page_setup.size.value} ({report.template.page_setup.orientation.value})",
            f"Editable Elements  : {report.editable_elements_count} header/footer element(s)",
            f"Visual Backdrop    : {'Yes (Static Reference)' if report.uses_visual_backdrop else 'No (100% Native Editable)'}",
            "",
            f"Summary: {report.summary_message}",
        ]
        if report.warnings:
            lines.append("")
            lines.append("Notes / Warnings:")
            for w in report.warnings:
                lines.append(f"  • {w}")

        self.report_view.setPlainText("\n".join(lines))
        self.confirm_btn.setEnabled(True)
        return report

    def _on_confirm_clicked(self) -> None:
        if self.imported_template is None:
            self.run_import_preview()
        if self.imported_template is not None:
            custom_name = self.template_name_edit.text().strip()
            if custom_name and custom_name != self.imported_template.name:
                self.imported_template = self.template_store.rename_template(
                    self.imported_template.template_id,
                    custom_name,
                )
            self.accept()
