"""Home Hub & Template Management Screen for Question Paper Studio.

Provides:
1. Quick Action Cards:
   - Create Question Paper (gated by template selection)
   - Create Template
   - Import Template (DOCX / PDF / .qpt)
   - Open Project (.qpf)
2. Available Templates Grid / List:
   - Preview, Select for New Paper, Edit, Rename, Duplicate, Delete (with confirmation;
     deleting a template never affects saved `.qpf` papers).
3. Saved & Recent Question Papers List:
   - Open, Duplicate Project, Export (PDF/DOCX), Delete.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.models.project_model import ProjectState
from src.core.models.template_model import Template
from src.core.storage.qpf_archive import QPFArchive
from src.core.storage.template_store import TemplateStore
from src.rendering.docx_exporter import DOCXExporter
from src.rendering.pdf_exporter import PDFExporter
from src.ui.home.template_import_dialog import TemplateImportDialog


class HomeScreen(QWidget):
    """Launcher hub for creating papers, managing visual templates, and opening saved `.qpf` projects."""

    # Signals emitted to MainWindow router
    create_paper_requested = Signal(Template, str)       # (selected_template, paper_title)
    open_project_requested = Signal(ProjectState, Path)  # (loaded_project, qpf_file_path)
    create_template_requested = Signal()
    edit_template_requested = Signal(Template)

    def __init__(
        self,
        template_store: TemplateStore,
        projects_dir: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.template_store = template_store
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

        self._templates: List[Template] = []
        self._selected_template_id: Optional[str] = None

        self._build_ui()
        self.refresh_templates()
        self.refresh_recent_projects()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(16)

        # 1. Header Banner
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        app_title = QLabel("Question Paper Studio")
        app_title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        app_sub = QLabel(
            "Template-Based Question Paper Creation & Management Studio — Simple by Default, Powerful When Needed"
        )
        app_sub.setStyleSheet("color: #475569; font-size: 10pt;")
        title_col.addWidget(app_title)
        title_col.addWidget(app_sub)
        header_row.addLayout(title_col, 1)
        root_layout.addLayout(header_row)

        # 2. Quick Action Bar (4 Primary Cards / Buttons)
        actions_frame = QFrame()
        actions_frame.setObjectName("CardFrame")
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setContentsMargins(14, 12, 14, 12)
        actions_layout.setSpacing(12)

        self.btn_create_paper = QPushButton("Create Question Paper")
        self.btn_create_paper.setObjectName("PrimaryButton")
        self.btn_create_paper.setMinimumHeight(40)
        self.btn_create_paper.setEnabled(False)
        self.btn_create_paper.setToolTip("Select a template below to start a new question paper.")
        self.btn_create_paper.clicked.connect(self.on_create_question_paper)

        self.btn_create_template = QPushButton("Create Template")
        self.btn_create_template.setMinimumHeight(40)
        self.btn_create_template.clicked.connect(self.create_template_requested.emit)

        self.btn_import_template = QPushButton("Import Template (DOCX/PDF/.qpt)")
        self.btn_import_template.setMinimumHeight(40)
        self.btn_import_template.clicked.connect(self.on_import_template_dialog)

        self.btn_open_project_file = QPushButton("Open Project (.qpf)")
        self.btn_open_project_file.setMinimumHeight(40)
        self.btn_open_project_file.clicked.connect(self.on_browse_and_open_qpf)

        actions_layout.addWidget(self.btn_create_paper)
        actions_layout.addWidget(self.btn_create_template)
        actions_layout.addWidget(self.btn_import_template)
        actions_layout.addWidget(self.btn_open_project_file)
        root_layout.addWidget(actions_frame)

        # 3. Main Content Splitter: Available Templates (Left) | Saved & Recent Question Papers (Right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel: Available Templates
        templates_panel = QFrame()
        templates_panel.setObjectName("CardFrame")
        t_layout = QVBoxLayout(templates_panel)
        t_layout.setContentsMargins(14, 14, 14, 14)
        t_layout.setSpacing(10)

        t_hdr = QLabel("Available Visual Templates (Select a Template to Create a Paper)")
        t_hdr.setStyleSheet("font-size: 11pt; font-weight: 700;")
        t_layout.addWidget(t_hdr)

        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_template_selection_changed)
        self.template_list.itemDoubleClicked.connect(lambda _: self.on_create_question_paper())
        t_layout.addWidget(self.template_list, 1)

        self.selected_template_status = QLabel("No template selected.")
        self.selected_template_status.setStyleSheet("color: #475569; font-style: italic;")
        t_layout.addWidget(self.selected_template_status)

        t_btn_row = QHBoxLayout()
        self.btn_preview_template = QPushButton("Preview")
        self.btn_preview_template.setEnabled(False)
        self.btn_preview_template.clicked.connect(self.on_preview_selected_template)

        self.btn_edit_template = QPushButton("Edit")
        self.btn_edit_template.setEnabled(False)
        self.btn_edit_template.clicked.connect(self.on_edit_selected_template)

        self.btn_rename_template = QPushButton("Rename")
        self.btn_rename_template.setEnabled(False)
        self.btn_rename_template.clicked.connect(self.on_rename_selected_template)

        self.btn_duplicate_template = QPushButton("Duplicate")
        self.btn_duplicate_template.setEnabled(False)
        self.btn_duplicate_template.clicked.connect(self.on_duplicate_selected_template)

        self.btn_delete_template = QPushButton("Delete")
        self.btn_delete_template.setObjectName("DangerButton")
        self.btn_delete_template.setEnabled(False)
        self.btn_delete_template.clicked.connect(self.on_delete_selected_template)

        t_btn_row.addWidget(self.btn_preview_template)
        t_btn_row.addWidget(self.btn_edit_template)
        t_btn_row.addWidget(self.btn_rename_template)
        t_btn_row.addWidget(self.btn_duplicate_template)
        t_btn_row.addWidget(self.btn_delete_template)
        t_layout.addLayout(t_btn_row)

        # Right Panel: Saved & Recent Question Papers
        projects_panel = QFrame()
        projects_panel.setObjectName("CardFrame")
        p_layout = QVBoxLayout(projects_panel)
        p_layout.setContentsMargins(14, 14, 14, 14)
        p_layout.setSpacing(10)

        p_hdr = QLabel("Saved & Recent Question Papers (.qpf)")
        p_hdr.setStyleSheet("font-size: 11pt; font-weight: 700;")
        p_layout.addWidget(p_hdr)

        self.project_list = QListWidget()
        self.project_list.currentItemChanged.connect(self._on_project_selection_changed)
        self.project_list.itemDoubleClicked.connect(lambda _: self.on_open_selected_project())
        p_layout.addWidget(self.project_list, 1)

        p_btn_row = QHBoxLayout()
        self.btn_open_recent = QPushButton("Open")
        self.btn_open_recent.setEnabled(False)
        self.btn_open_recent.clicked.connect(self.on_open_selected_project)

        self.btn_duplicate_project = QPushButton("Duplicate Project")
        self.btn_duplicate_project.setEnabled(False)
        self.btn_duplicate_project.clicked.connect(self.on_duplicate_selected_project)

        self.btn_export_project = QPushButton("Export PDF/DOCX")
        self.btn_export_project.setEnabled(False)
        self.btn_export_project.clicked.connect(self.on_quick_export_selected_project)

        self.btn_delete_project = QPushButton("Delete")
        self.btn_delete_project.setObjectName("DangerButton")
        self.btn_delete_project.setEnabled(False)
        self.btn_delete_project.clicked.connect(self.on_delete_selected_project)

        p_btn_row.addWidget(self.btn_open_recent)
        p_btn_row.addWidget(self.btn_duplicate_project)
        p_btn_row.addWidget(self.btn_export_project)
        p_btn_row.addWidget(self.btn_delete_project)
        p_layout.addLayout(p_btn_row)

        splitter.addWidget(templates_panel)
        splitter.addWidget(projects_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root_layout.addWidget(splitter, 1)

    # ========================================================================
    # Template Management Actions
    # ========================================================================

    def refresh_templates(self, select_template_id: Optional[str] = None) -> None:
        """Reload templates from `self.template_store` and populate the template list."""
        target_id = select_template_id or self._selected_template_id
        self.template_list.clear()
        self._templates = self.template_store.list_templates()

        selected_row = -1
        for idx, tmpl in enumerate(self._templates):
            badge = "[Built-in]" if tmpl.is_builtin else "[Custom]"
            dims = tmpl.page_setup.effective_dimensions_mm
            label = (
                f"{tmpl.name}  {badge}\n"
                f"Page: {tmpl.page_setup.size.value} ({dims[0]:g}×{dims[1]:g} mm, {tmpl.page_setup.orientation.value}) | "
                f"Header: {tmpl.header_height_mm:g} mm | Footer: {tmpl.footer_height_mm:g} mm"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tmpl.template_id)
            self.template_list.addItem(item)
            if target_id and tmpl.template_id == target_id:
                selected_row = idx

        if selected_row >= 0:
            self.template_list.setCurrentRow(selected_row)
        else:
            self._selected_template_id = None
            self._update_template_action_states()

    def select_template_by_id(self, template_id: Optional[str]) -> bool:
        """Programmatically select a template by ID (or clear selection when `None`)."""
        if template_id is None:
            self.template_list.clearSelection()
            self.template_list.setCurrentRow(-1)
            self._selected_template_id = None
            self._update_template_action_states()
            return True

        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == template_id:
                self.template_list.setCurrentRow(row)
                return True
        return False

    def get_selected_template(self) -> Optional[Template]:
        """Return the currently selected `Template` or `None`."""
        if not self._selected_template_id:
            return None
        return self.template_store.get_template(self._selected_template_id)

    def _on_template_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        if current is None:
            self._selected_template_id = None
        else:
            self._selected_template_id = str(current.data(Qt.ItemDataRole.UserRole))
        self._update_template_action_states()

    def _update_template_action_states(self) -> None:
        tmpl = self.get_selected_template()
        has_sel = tmpl is not None
        self.btn_create_paper.setEnabled(has_sel)
        self.btn_preview_template.setEnabled(has_sel)
        self.btn_edit_template.setEnabled(has_sel)
        self.btn_rename_template.setEnabled(has_sel)
        self.btn_duplicate_template.setEnabled(has_sel)
        self.btn_delete_template.setEnabled(has_sel)

        if tmpl is not None:
            self.selected_template_status.setText(
                f"Selected Template: {tmpl.name} ({tmpl.page_setup.size.value} {tmpl.page_setup.orientation.value})"
            )
        else:
            self.selected_template_status.setText(
                "Please select a template above before creating a new question paper."
            )

    def on_create_question_paper(self, paper_title: str = "Untitled Question Paper") -> bool:
        """Start a new question paper from the selected template (enforcing template selection gate)."""
        tmpl = self.get_selected_template()
        if tmpl is None:
            QMessageBox.information(
                self,
                "Template Selection Required",
                "Please select a visual template first before creating a question paper.",
            )
            return False

        self.create_paper_requested.emit(tmpl, paper_title or "Untitled Question Paper")
        return True

    def on_preview_selected_template(self) -> None:
        """Display a clean summary preview of the selected template's page setup and header/footer elements."""
        tmpl = self.get_selected_template()
        if tmpl is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Template Preview — {tmpl.name}")
        dlg.resize(520, 380)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)

        hdr_els = tmpl.get_header_elements(is_first_page=True)
        ftr_els = tmpl.get_footer_elements(is_first_page=True)
        lines = [
            f"Template Name        : {tmpl.name}",
            f"Page Size            : {tmpl.page_setup.size.value} ({tmpl.page_setup.orientation.value})",
            f"Margins (T/B/L/R)    : {tmpl.page_setup.margins_mm.top} / {tmpl.page_setup.margins_mm.bottom} / "
            f"{tmpl.page_setup.margins_mm.left} / {tmpl.page_setup.margins_mm.right} mm",
            f"Header Zone Height   : {tmpl.header_height_mm} mm ({len(hdr_els)} element(s))",
            f"Footer Zone Height   : {tmpl.footer_height_mm} mm ({len(ftr_els)} element(s))",
            f"Different First Page : {'Yes' if tmpl.different_first_page else 'No'}",
            "",
            "Header Elements:",
        ]
        for el in hdr_els:
            lines.append(f"  • [{el.element_type.value.upper()}] ({el.x_mm}mm, {el.y_mm}mm): {el.content}")
        lines.append("")
        lines.append("Footer Elements:")
        for el in ftr_els:
            lines.append(f"  • [{el.element_type.value.upper()}] ({el.x_mm}mm, {el.y_mm}mm): {el.content}")

        txt.setPlainText("\n".join(lines))
        lay.addWidget(txt)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()

    def on_edit_selected_template(self) -> None:
        tmpl = self.get_selected_template()
        if tmpl is not None:
            self.edit_template_requested.emit(tmpl)

    def on_rename_selected_template(self, new_name: Optional[str] = None) -> Optional[Template]:
        """Rename the selected template."""
        tmpl = self.get_selected_template()
        if tmpl is None:
            return None

        if new_name is None:
            entered, ok = QInputDialog.getText(
                self,
                "Rename Template",
                "Enter new template name:",
                text=tmpl.name,
            )
            if not ok or not entered.strip():
                return None
            new_name = entered.strip()

        updated = self.template_store.rename_template(tmpl.template_id, new_name)
        self.refresh_templates(select_template_id=updated.template_id)
        return updated

    def on_duplicate_selected_template(self, new_name: Optional[str] = None) -> Optional[Template]:
        """Duplicate the selected template and select the newly created copy."""
        tmpl = self.get_selected_template()
        if tmpl is None:
            return None

        cloned = self.template_store.duplicate_template(tmpl.template_id, new_name=new_name)
        self.refresh_templates(select_template_id=cloned.template_id)
        return cloned

    def on_delete_selected_template(self, confirm: bool = False) -> bool:
        """Delete the selected template after confirmation (never affects saved `.qpf` papers)."""
        tmpl = self.get_selected_template()
        if tmpl is None:
            return False

        if not confirm:
            ans = QMessageBox.question(
                self,
                "Delete Template",
                f"Are you sure you want to delete template '{tmpl.name}'?\n\n"
                "Previously saved question papers (.qpf) embed their own snapshot and will NOT be affected.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        deleted = self.template_store.delete_template(tmpl.template_id)
        if deleted:
            self._selected_template_id = None
            self.refresh_templates()
        return deleted

    def on_import_template_dialog(self, file_path: Optional[Path] = None) -> Optional[Template]:
        """Launch `TemplateImportDialog` and refresh the template grid upon completion."""
        dlg = TemplateImportDialog(self.template_store, parent=self, initial_file_path=file_path)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.imported_template is not None:
            imported = dlg.imported_template
            self.refresh_templates(select_template_id=imported.template_id)
            return imported
        return None

    # ========================================================================
    # Saved & Recent Question Papers (.qpf) Actions
    # ========================================================================

    def refresh_recent_projects(self) -> None:
        """Scan `self.projects_dir` for saved `.qpf` archives and populate the projects list."""
        self.project_list.clear()
        for qpf_path in sorted(self.projects_dir.glob("*.qpf"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                unpack = QPFArchive.load_qpf(qpf_path)
                proj = unpack.project
                q_count = len(proj.all_questions_dfs())
                label = (
                    f"{proj.title}  ({qpf_path.name})\n"
                    f"Template: {proj.template_snapshot.name} | Questions: {q_count}"
                )
            except Exception:
                label = f"{qpf_path.stem}  ({qpf_path.name})"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(qpf_path))
            self.project_list.addItem(item)

        self._on_project_selection_changed(self.project_list.currentItem(), None)

    def _on_project_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        has_proj = current is not None
        self.btn_open_recent.setEnabled(has_proj)
        self.btn_duplicate_project.setEnabled(has_proj)
        self.btn_export_project.setEnabled(has_proj)
        self.btn_delete_project.setEnabled(has_proj)

    def get_selected_project_path(self) -> Optional[Path]:
        item = self.project_list.currentItem()
        if item is None:
            return None
        return Path(str(item.data(Qt.ItemDataRole.UserRole)))

    def on_open_selected_project(self) -> Optional[ProjectState]:
        """Open the selected `.qpf` project from the recent list."""
        qpf_path = self.get_selected_project_path()
        if qpf_path is None or not qpf_path.exists():
            return None
        unpack = QPFArchive.load_qpf(qpf_path)
        self.open_project_requested.emit(unpack.project, qpf_path)
        return unpack.project

    def on_browse_and_open_qpf(self, file_path: Optional[Path] = None) -> Optional[ProjectState]:
        """Browse for a `.qpf` file on disk and open it."""
        chosen_path = file_path
        if chosen_path is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                "Open Question Paper Project (.qpf)",
                str(self.projects_dir),
                "Question Paper Files (*.qpf);;All Files (*.*)",
            )
            if not chosen:
                return None
            chosen_path = Path(chosen)

        unpack = QPFArchive.load_qpf(chosen_path)
        self.open_project_requested.emit(unpack.project, chosen_path)
        return unpack.project

    def on_duplicate_selected_project(self) -> Optional[Path]:
        """Duplicate the selected `.qpf` project file inside `self.projects_dir`."""
        qpf_path = self.get_selected_project_path()
        if qpf_path is None or not qpf_path.exists():
            return None

        unpack = QPFArchive.load_qpf(qpf_path)
        proj = unpack.project
        proj.title = f"{proj.title} (Copy)"
        new_path = self.projects_dir / f"{qpf_path.stem}_copy.qpf"
        counter = 1
        while new_path.exists():
            counter += 1
            new_path = self.projects_dir / f"{qpf_path.stem}_copy_{counter}.qpf"

        QPFArchive.save_qpf(proj, new_path, overwrite=True)
        self.refresh_recent_projects()
        return new_path

    def on_quick_export_selected_project(self, dest_dir: Optional[Path] = None) -> Optional[Path]:
        """Export the selected `.qpf` project directly to both PDF and DOCX."""
        qpf_path = self.get_selected_project_path()
        if qpf_path is None or not qpf_path.exists():
            return None

        target_dir = dest_dir or qpf_path.parent
        unpack = QPFArchive.load_qpf(qpf_path)
        proj = unpack.project
        pdf_out = PDFExporter.export_project_to_pdf(proj, target_dir / f"{qpf_path.stem}.pdf")
        DOCXExporter.export_project_to_docx(proj, target_dir / f"{qpf_path.stem}.docx")
        return pdf_out

    def on_delete_selected_project(self, confirm: bool = False) -> bool:
        """Delete the selected `.qpf` project file from `self.projects_dir`."""
        qpf_path = self.get_selected_project_path()
        if qpf_path is None or not qpf_path.exists():
            return False

        if not confirm:
            ans = QMessageBox.question(
                self,
                "Delete Question Paper",
                f"Are you sure you want to delete '{qpf_path.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        qpf_path.unlink()
        extracted_dir = qpf_path.parent / f".{qpf_path.stem}_assets"
        if extracted_dir.exists():
            shutil.rmtree(extracted_dir, ignore_errors=True)
        self.refresh_recent_projects()
        return True
