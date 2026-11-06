"""3-Pane Question Paper Creation Workspace Shell Window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import QuestionTreeEngine, UndoRedoManager
from src.core.engine.time_estimator import TimeEstimator
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.template_model import Template
from src.core.storage.qpf_archive import QPFArchive
from src.core.storage.template_store import TemplateStore
from src.ui.workspace.exam_info_bar import ExamInfoBar
from src.ui.workspace.outline_tree import OutlineTreeWidget


class WorkspaceScreen(QWidget):
    """3-Pane workspace shell orchestrating outline tree, question editing, and live print preview."""

    back_to_home_requested = Signal()
    project_saved = Signal(Path)

    def __init__(
        self,
        template_store: Optional[TemplateStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.template_store = template_store or TemplateStore()
        self.project: Optional[ProjectState] = None
        self.current_qpf_path: Optional[Path] = None
        self.has_unsaved_changes: bool = False

        self.undo_manager = UndoRedoManager()
        self._block_signals = False

        self._build_ui()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(8, 8, 8, 8)
        root_lay.setSpacing(6)

        # 1. Top Workspace Toolbar
        tb_frame = QFrame()
        tb_frame.setObjectName("CardFrame")
        tb_frame.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border-bottom: 1px solid #CBD5E1; padding: 4px; }"
        )
        tb_lay = QHBoxLayout(tb_frame)
        tb_lay.setContentsMargins(8, 4, 8, 4)
        tb_lay.setSpacing(8)

        self.btn_back = QPushButton("← Home")
        self.btn_back.clicked.connect(self._on_back_clicked)
        tb_lay.addWidget(self.btn_back)

        self.btn_save = QPushButton("💾 Save Paper (.qpf)")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self.save_project)
        tb_lay.addWidget(self.btn_save)

        tb_lay.addSpacing(6)

        self.btn_undo = QPushButton("↶ Undo")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("↷ Redo")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.redo)
        tb_lay.addWidget(self.btn_undo)
        tb_lay.addWidget(self.btn_redo)

        tb_lay.addSpacing(8)

        # Template hot-swapping dropdown
        tmpl_lbl = QLabel("Template:")
        tmpl_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.combo_template = QComboBox()
        self.combo_template.setMinimumWidth(180)
        self._populate_template_selector()
        self.combo_template.currentIndexChanged.connect(self._on_template_selected_index_changed)
        tb_lay.addWidget(tmpl_lbl)
        tb_lay.addWidget(self.combo_template)

        tb_lay.addStretch(1)

        self.btn_export = QPushButton("📤 Export (PDF / Word)")
        tb_lay.addWidget(self.btn_export)

        self.btn_print = QPushButton("🖨 Print")
        tb_lay.addWidget(self.btn_print)

        self.btn_toggle_preview = QPushButton("👁 Live Preview")
        self.btn_toggle_preview.setCheckable(True)
        self.btn_toggle_preview.setChecked(True)
        self.btn_toggle_preview.clicked.connect(self._toggle_preview_pane)
        tb_lay.addWidget(self.btn_toggle_preview)

        root_lay.addWidget(tb_frame)

        # 2. Collapsible Examination Header Bar
        self.info_bar = ExamInfoBar(self)
        self.info_bar.metadata_changed.connect(self._on_info_bar_changed)
        root_lay.addWidget(self.info_bar)

        # 3. Main 3-Pane Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Pane: Hierarchical Outline Tree
        self.outline_tree = OutlineTreeWidget(self)
        self.outline_tree.question_selected.connect(self._on_question_selected)
        self.outline_tree.section_selected.connect(self._on_section_selected)
        self.outline_tree.tree_structure_changed.connect(self._on_tree_structure_changed)
        self.splitter.addWidget(self.outline_tree)

        # Center Pane: Active Question Editor Container
        self.center_editor_container = QFrame()
        self.center_editor_container.setObjectName("CardFrame")
        self.center_editor_container.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; }"
        )
        self._build_center_pane_ui()
        self.splitter.addWidget(self.center_editor_container)

        # Right Pane: Live Summary & Paper Statistics Panel
        self.right_preview_container = QFrame()
        self.right_preview_container.setObjectName("CardFrame")
        self.right_preview_container.setStyleSheet(
            "#CardFrame { background-color: #FAFAFA; border: 1px solid #E2E8F0; border-radius: 6px; }"
        )
        self._build_right_pane_ui()
        self.splitter.addWidget(self.right_preview_container)

        # Splitter sizing: Left (280px), Center (stretch), Right (320px)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 2)
        root_lay.addWidget(self.splitter, 1)

        # 4. Bottom Status Bar
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setStyleSheet(
            "background-color: #0F172A; color: #FFFFFF; border-radius: 4px; padding: 4px 10px;"
        )
        sb_lay = QHBoxLayout(self.status_bar_frame)
        sb_lay.setContentsMargins(10, 4, 10, 4)

        self.lbl_status_marks = QLabel("Marks: 0 / 100")
        self.lbl_status_marks.setStyleSheet("font-weight: 700; color: #38BDF8;")
        sb_lay.addWidget(self.lbl_status_marks)

        sb_lay.addSpacing(16)

        self.lbl_status_balance = QLabel("✓ Balanced")
        self.lbl_status_balance.setStyleSheet("font-weight: 600; color: #4ADE80;")
        sb_lay.addWidget(self.lbl_status_balance)

        sb_lay.addSpacing(16)

        self.lbl_status_time = QLabel("Time: ~0 min")
        self.lbl_status_time.setStyleSheet("color: #E2E8F0;")
        sb_lay.addWidget(self.lbl_status_time)

        sb_lay.addSpacing(16)

        self.lbl_status_qcount = QLabel("Questions: 0")
        self.lbl_status_qcount.setStyleSheet("color: #E2E8F0;")
        sb_lay.addWidget(self.lbl_status_qcount)

        sb_lay.addStretch(1)

        self.lbl_status_save = QLabel("Ready")
        self.lbl_status_save.setStyleSheet("color: #94A3B8;")
        sb_lay.addWidget(self.lbl_status_save)

        root_lay.addWidget(self.status_bar_frame)

    def _build_center_pane_ui(self) -> None:
        """Construct the center question editor container."""
        lay = QVBoxLayout(self.center_editor_container)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Header for active question
        self.lbl_active_header = QLabel("Question Editor")
        self.lbl_active_header.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0F172A;")
        lay.addWidget(self.lbl_active_header)

        self.lbl_active_meta = QLabel("Select a question from the outline tree on the left to edit.")
        self.lbl_active_meta.setStyleSheet("color: #64748B; font-size: 10pt;")
        lay.addWidget(self.lbl_active_meta)

        # Question Content Preview Frame (ready to receive Phase 4.2 RichTextEditor)
        self.editor_slot = QFrame()
        self.editor_slot.setStyleSheet("background-color: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 4px;")
        slot_lay = QVBoxLayout(self.editor_slot)
        slot_lay.setContentsMargins(16, 16, 16, 16)

        self.lbl_editor_preview = QLabel("Question body will appear here.")
        self.lbl_editor_preview.setWordWrap(True)
        self.lbl_editor_preview.setStyleSheet("color: #334155; font-size: 11pt;")
        slot_lay.addWidget(self.lbl_editor_preview)
        slot_lay.addStretch(1)

        lay.addWidget(self.editor_slot, 1)

    def _build_right_pane_ui(self) -> None:
        """Construct the right-hand paper summary & statistics container."""
        lay = QVBoxLayout(self.right_preview_container)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title_lbl = QLabel("📊 Paper Blueprint & Marks Audit")
        title_lbl.setStyleSheet("font-size: 11pt; font-weight: 700; color: #1E293B;")
        lay.addWidget(title_lbl)

        # Marks summary card
        self.card_marks = QFrame()
        self.card_marks.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        card_lay = QVBoxLayout(self.card_marks)
        card_lay.setSpacing(4)

        self.lbl_audit_marks = QLabel("Total Allocated: 0 M")
        self.lbl_audit_marks.setStyleSheet("font-size: 12pt; font-weight: 700; color: #2563EB;")
        self.lbl_audit_target = QLabel("Maximum Marks Target: 100 M")
        self.lbl_audit_target.setStyleSheet("font-size: 10pt; color: #64748B;")
        self.lbl_audit_status = QLabel("✓ Balanced")
        self.lbl_audit_status.setStyleSheet("font-size: 10pt; font-weight: 600; color: #16A34A;")

        card_lay.addWidget(self.lbl_audit_marks)
        card_lay.addWidget(self.lbl_audit_target)
        card_lay.addWidget(self.lbl_audit_status)
        lay.addWidget(self.card_marks)

        # Section-wise marks breakdown table
        sec_lbl = QLabel("Section Marks Breakdown:")
        sec_lbl.setStyleSheet("font-weight: 600; color: #475569; margin-top: 6px;")
        lay.addWidget(sec_lbl)

        self.table_sections = QTableWidget(0, 3)
        self.table_sections.setHorizontalHeaderLabels(["Section", "Questions", "Marks"])
        self.table_sections.horizontalHeader().setStretchLastSection(True)
        self.table_sections.setAlternatingRowColors(True)
        self.table_sections.setMaximumHeight(160)
        lay.addWidget(self.table_sections)

        # Estimated time card
        self.card_time = QFrame()
        self.card_time.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;")
        t_lay = QVBoxLayout(self.card_time)
        self.lbl_est_time = QLabel("⏱ Estimated Exam Duration: 0 mins")
        self.lbl_est_time.setStyleSheet("font-weight: 600; color: #0284C7;")
        t_lay.addWidget(self.lbl_est_time)
        lay.addWidget(self.card_time)

        lay.addStretch(1)

    def _populate_template_selector(self) -> None:
        self.combo_template.clear()
        for tmpl in self.template_store.list_templates():
            tag = " [Built-in]" if tmpl.is_builtin else ""
            self.combo_template.addItem(f"{tmpl.name}{tag}", tmpl.template_id)

    def _toggle_preview_pane(self) -> None:
        is_visible = self.btn_toggle_preview.isChecked()
        self.right_preview_container.setVisible(is_visible)

    # ========================================================================
    # Project Loading, Saving & State Management
    # ========================================================================

    def load_project(
        self,
        project: ProjectState,
        qpf_path: Optional[Path] = None,
    ) -> None:
        """Load `project` state into workspace components."""
        self._block_signals = True
        try:
            self.project = project
            self.current_qpf_path = qpf_path
            self.has_unsaved_changes = False

            # Initialize undo stack cleanly with starting baseline snapshot
            self.undo_manager.clear()
            self.undo_manager.record_state(project, "Initial State")
            self._update_undo_redo_buttons()

            # Synchronize template selector
            t_id = project.template_snapshot.template_id
            idx = self.combo_template.findData(t_id)
            if idx >= 0:
                self.combo_template.setCurrentIndex(idx)

            # Load into info bar and outline tree
            self.info_bar.load_from_project(project)
            self.outline_tree.load_project(project)

            self.refresh_status_and_summary()
            self.lbl_status_save.setText(f"Loaded: {project.title}")
        finally:
            self._block_signals = False

    def save_project(self, custom_path: Optional[Path | str] = None) -> Path:
        """Save active project to `.qpf` archive."""
        if not self.project:
            raise RuntimeError("No active project to save.")

        self.info_bar.save_to_project(self.project)

        target_path: Path
        if custom_path:
            target_path = Path(custom_path)
        elif self.current_qpf_path:
            target_path = self.current_qpf_path
        else:
            safe_name = "".join(c for c in self.project.title if c.isalnum() or c in ("-", "_", " ")).strip()
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                "Save Question Paper Project",
                f"{safe_name}.qpf",
                "Question Paper Files (*.qpf)",
            )
            if not chosen:
                return self.current_qpf_path or Path(f"{safe_name}.qpf")
            target_path = Path(chosen)

        saved = QPFArchive.save_qpf(self.project, target_path, overwrite=True)
        self.current_qpf_path = saved
        self.has_unsaved_changes = False
        self.lbl_status_save.setText(f"Saved to {saved.name}")
        self.project_saved.emit(saved)
        return saved

    def record_undo_state(self, description: str = "Edit") -> None:
        """Record current project state into the undo history stack."""
        if not self.project or self._block_signals:
            return
        self.info_bar.save_to_project(self.project)
        self.undo_manager.record_state(self.project, description)
        self.has_unsaved_changes = True
        self.lbl_status_save.setText("Unsaved changes*")
        self._update_undo_redo_buttons()
        self.refresh_status_and_summary()

    def undo(self) -> None:
        """Undo last project modification."""
        if not self.project or len(self.undo_manager._undo_stack) <= 1:
            return
        reverted = self.undo_manager.undo(self.project)
        self.project = reverted
        self.info_bar.load_from_project(reverted)
        self.outline_tree.load_project(reverted)
        self.has_unsaved_changes = True
        self.lbl_status_save.setText("Undone")
        self._update_undo_redo_buttons()
        self.refresh_status_and_summary()

    def redo(self) -> None:
        """Redo previously undone project modification."""
        if not self.project or not self.undo_manager.can_redo:
            return
        restored = self.undo_manager.redo(self.project)
        self.project = restored
        self.info_bar.load_from_project(restored)
        self.outline_tree.load_project(restored)
        self.has_unsaved_changes = True
        self.lbl_status_save.setText("Redone")
        self._update_undo_redo_buttons()
        self.refresh_status_and_summary()

    def _update_undo_redo_buttons(self) -> None:
        can_undo = len(self.undo_manager._undo_stack) > 1
        self.btn_undo.setEnabled(can_undo)
        u_desc = self.undo_manager.undo_description if can_undo else None
        self.btn_undo.setToolTip(f"Undo: {u_desc}" if u_desc else "Undo")

        self.btn_redo.setEnabled(self.undo_manager.can_redo)
        r_desc = self.undo_manager.redo_description
        self.btn_redo.setToolTip(f"Redo: {r_desc}" if r_desc else "Redo")

    # ========================================================================
    # Template Hot-Swapping
    # ========================================================================

    def _on_template_selected_index_changed(self, index: int) -> None:
        if self._block_signals or not self.project:
            return
        tmpl_id = self.combo_template.currentData()
        if not tmpl_id:
            return

        tmpl = self.template_store.get_template(tmpl_id)
        if tmpl and tmpl.template_id != self.project.template_snapshot.template_id:
            self.project.apply_template(tmpl)
            self.record_undo_state(f"Change Template to {tmpl.name}")

    # ========================================================================
    # Event Handlers & View Synchronization
    # ========================================================================

    def _on_info_bar_changed(self) -> None:
        if self._block_signals or not self.project:
            return
        self.info_bar.save_to_project(self.project)
        self.has_unsaved_changes = True
        self.lbl_status_save.setText("Unsaved changes*")
        self.refresh_status_and_summary()

    def _on_tree_structure_changed(self, description: str) -> None:
        self.record_undo_state(description)

    def _on_question_selected(self, question_id: str) -> None:
        if not self.project:
            return
        lookup = QuestionTreeEngine.find_node(self.project, question_id)
        if not lookup:
            return

        node: QuestionNode = lookup.node
        self.lbl_active_header.setText(f"{node.resolved_number or '•'} Question ({node.question_type.value})")
        clean_text = self.outline_tree._strip_html(node.prompt_html or "").strip()
        marks = MarksEngine.calculate_question_effective_marks(node).effective_marks
        marks_str = f"{int(marks)} M" if marks.is_integer() else f"{marks:g} M"
        self.lbl_active_meta.setText(f"Marks: {marks_str}  |  Section: {lookup.section.title if lookup.section else 'Main'}")
        self.lbl_editor_preview.setText(clean_text or "[Empty Question Content]")

    def _on_section_selected(self, section_id: str) -> None:
        if not self.project:
            return
        sec = QuestionTreeEngine.find_section(self.project, section_id)
        if not sec:
            return
        self.lbl_active_header.setText(f"📁 {sec.title}")
        self.lbl_active_meta.setText(f"Contains {len(sec.questions)} top-level question(s).")
        self.lbl_editor_preview.setText(sec.instructions_html or "[No section instructions specified]")

    def refresh_status_and_summary(self) -> None:
        """Run audit calculations and update status bar indicators and right summary pane."""
        if not self.project:
            return

        report = MarksEngine.audit_paper(self.project)
        time_rep = TimeEstimator.estimate_paper_time_minutes(self.project)
        q_count = len(self.project.all_questions_dfs())

        # Status Bar Update
        tot_marks = report.total_paper_marks
        max_marks = report.max_marks or 0.0
        tot_str = f"{int(tot_marks)}" if float(tot_marks).is_integer() else f"{tot_marks:g}"
        max_str = f"{int(max_marks)}" if float(max_marks).is_integer() else f"{max_marks:g}"
        self.lbl_status_marks.setText(f"Marks: {tot_str} / {max_str}")

        if report.is_balanced:
            self.lbl_status_balance.setText("✓ Balanced")
            self.lbl_status_balance.setStyleSheet("font-weight: 600; color: #4ADE80;")
        else:
            delta_str = f"{int(report.discrepancy_delta):+d}" if float(report.discrepancy_delta).is_integer() else f"{report.discrepancy_delta:+g}"
            self.lbl_status_balance.setText(f"⚠ Mismatch {delta_str} M")
            self.lbl_status_balance.setStyleSheet("font-weight: 700; color: #F59E0B;")

        self.lbl_status_time.setText(f"Time: ~{int(time_rep.total_estimated_minutes)} min")
        self.lbl_status_qcount.setText(f"Questions: {q_count}")

        # Right Summary Panel Update
        self.lbl_audit_marks.setText(f"Total Allocated: {tot_str} M")
        self.lbl_audit_target.setText(f"Target Max Marks: {max_str} M")
        if report.is_balanced:
            self.lbl_audit_status.setText("✓ Balanced — Marks match target")
            self.lbl_audit_status.setStyleSheet("font-size: 10pt; font-weight: 600; color: #16A34A;")
        else:
            delta = report.discrepancy_delta
            d_text = f"Allocated is {abs(delta):g} M {'over' if delta > 0 else 'under'} target"
            self.lbl_audit_status.setText(f"⚠ Discrepancy: {d_text}")
            self.lbl_audit_status.setStyleSheet("font-size: 10pt; font-weight: 700; color: #D97706;")

        self.lbl_est_time.setText(f"⏱ Estimated Duration: {int(time_rep.total_estimated_minutes)} mins")

        # Section Table Update
        self.table_sections.setRowCount(len(self.project.sections))
        for r, s in enumerate(self.project.sections):
            sec_summary = MarksEngine.calculate_section_marks(s)
            s_marks = sec_summary.total_effective_marks
            sm_str = f"{int(s_marks)} M" if float(s_marks).is_integer() else f"{s_marks:g} M"
            self.table_sections.setItem(r, 0, QTableWidgetItem(s.title))
            self.table_sections.setItem(r, 1, QTableWidgetItem(str(len(s.questions))))
            self.table_sections.setItem(r, 2, QTableWidgetItem(sm_str))

    def _on_back_clicked(self) -> None:
        if self.has_unsaved_changes:
            ans = QMessageBox.question(
                self,
                "Unsaved Question Paper",
                "You have unsaved changes in this question paper. Return to Home without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.back_to_home_requested.emit()
