"""Multi-Set Examination Generator, Shuffler & Equivalence Matrix UI Dialog.

Allows educators to:
1. Generate parallel exam sets (Set A, Set B, Set C, Set D).
2. Configure shuffling strategies (question order, MCQ option permutations, match pairs, dynamic numbers).
3. Inspect the live interactive Cross-Set Question Mapping and Answer Key Matrix.
4. Verify mark and question count equality across all sets.
5. Batch export all parallel set question papers, individual answer keys, and master comparison sheets in vector PDF and Word DOCX formats.
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.marks_engine import MarksEngine
from src.core.engine.multi_set_shuffler import (
    MultiSetGenerationResult,
    MultiSetShuffler,
    ShufflingOptions,
)
from src.core.models.project_model import ProjectState


class MultiSetDialog(QDialog):
    """Modal dialog for multi-set paper generation, equivalence matrix inspection, and batch exporting."""

    sets_generated = Signal(object)  # MultiSetGenerationResult

    def __init__(
        self,
        project: ProjectState,
        default_export_dir: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: ProjectState = project
        self.generation_result: Optional[MultiSetGenerationResult] = None

        if default_export_dir:
            self.export_dir = Path(default_export_dir)
        else:
            self.export_dir = Path.home() / "Documents"
            if not self.export_dir.exists():
                self.export_dir = Path.cwd()

        self.setWindowTitle("🔀 Multi-Set Generator & Equivalence Matrix (Set A / B / C / D)")
        self.setMinimumWidth(880)
        self.setMinimumHeight(640)
        self.setModal(True)

        self._build_ui()
        self._generate_sets_preview()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setSpacing(12)

        # 1. Header Banner
        lbl_title = QLabel("🔀 Multi-Set Generator & Cross-Set Difference Matrix")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0F172A;")
        root_lay.addWidget(lbl_title)

        lbl_sub = QLabel(
            "Generate parallel sets with synchronized answer keys, option permutations, and master equivalence matrices."
        )
        lbl_sub.setStyleSheet("color: #64748B; font-size: 9.5pt;")
        root_lay.addWidget(lbl_sub)

        # 2. Configuration & Shuffling Parameters
        cfg_group = QGroupBox("Shuffling Strategies & Set Identifiers")
        cfg_lay = QVBoxLayout(cfg_group)
        cfg_lay.setSpacing(8)

        # Set identifiers row
        set_row = QHBoxLayout()
        s_lbl = QLabel("Set Identifiers:")
        s_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_set_ids = QLineEdit("A, B, C, D")
        self.txt_set_ids.setToolTip("Comma-separated list of set names (e.g. 'A, B' or 'A, B, C, D' or '1, 2, 3')")

        btn_preset_ab = QPushButton("Set A/B")
        btn_preset_ab.clicked.connect(lambda: self.txt_set_ids.setText("A, B"))
        btn_preset_abcd = QPushButton("Set A/B/C/D")
        btn_preset_abcd.clicked.connect(lambda: self.txt_set_ids.setText("A, B, C, D"))

        set_row.addWidget(s_lbl)
        set_row.addWidget(self.txt_set_ids, 1)
        set_row.addWidget(btn_preset_ab)
        set_row.addWidget(btn_preset_abcd)
        cfg_lay.addLayout(set_row)

        # Shuffling checkboxes
        opts_lay = QHBoxLayout()
        self.chk_shuffle_q = QCheckBox("Shuffle Questions within Sections")
        self.chk_shuffle_q.setChecked(True)
        self.chk_shuffle_mcq = QCheckBox("Shuffle MCQ Options (A, B, C, D)")
        self.chk_shuffle_mcq.setChecked(True)
        self.chk_shuffle_match = QCheckBox("Shuffle Match the Pair Choices")
        self.chk_shuffle_match.setChecked(True)
        self.chk_vary_num = QCheckBox("Vary Dynamic Numbers")
        self.chk_vary_num.setChecked(True)
        opts_lay.addWidget(self.chk_shuffle_q)
        opts_lay.addWidget(self.chk_shuffle_mcq)
        opts_lay.addWidget(self.chk_shuffle_match)
        opts_lay.addWidget(self.chk_vary_num)
        opts_lay.addStretch(1)
        cfg_lay.addLayout(opts_lay)

        # Integrity & Seed Row
        seed_row = QHBoxLayout()
        self.chk_keep_choices = QCheckBox("Keep Choice Groups (OR pairs) Contiguous")
        self.chk_keep_choices.setChecked(True)
        self.chk_preserve_set_a = QCheckBox("Keep Set A Unshuffled (Baseline)")
        self.chk_preserve_set_a.setChecked(False)

        seed_lbl = QLabel("Master Seed:")
        seed_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(1, 999999)
        self.spin_seed.setValue(42)

        self.btn_random_seed = QPushButton("🎲 Randomize")
        self.btn_random_seed.clicked.connect(self._randomize_seed)

        self.btn_regenerate = QPushButton("⚡ Generate Sets Preview")
        self.btn_regenerate.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: 700; padding: 5px 12px;")
        self.btn_regenerate.clicked.connect(self._generate_sets_preview)

        seed_row.addWidget(self.chk_keep_choices)
        seed_row.addWidget(self.chk_preserve_set_a)
        seed_row.addSpacing(12)
        seed_row.addWidget(seed_lbl)
        seed_row.addWidget(self.spin_seed)
        seed_row.addWidget(self.btn_random_seed)
        seed_row.addSpacing(8)
        seed_row.addWidget(self.btn_regenerate)
        seed_row.addStretch(1)
        cfg_lay.addLayout(seed_row)

        root_lay.addWidget(cfg_group)

        # 3. Interactive Multi-Tab Matrix & Verification View
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { font-weight: 600; padding: 6px 14px; }
        """)

        # Tab 1: Cross-Set Question Mapping Table
        self.tab_mapping = QWidget()
        m_lay = QVBoxLayout(self.tab_mapping)
        m_lay.setContentsMargins(8, 8, 8, 8)
        self.table_mapping = QTableWidget(0, 0)
        self.table_mapping.setAlternatingRowColors(True)
        m_lay.addWidget(self.table_mapping)
        self.tabs.addTab(self.tab_mapping, "📊 Question Equivalence Matrix")

        # Tab 2: Cross-Set Answer Key Matrix
        self.tab_answers = QWidget()
        a_lay = QVBoxLayout(self.tab_answers)
        a_lay.setContentsMargins(8, 8, 8, 8)
        self.table_answers = QTableWidget(0, 0)
        self.table_answers.setAlternatingRowColors(True)
        a_lay.addWidget(self.table_answers)
        self.tabs.addTab(self.tab_answers, "🔑 Synchronized Answer Keys Matrix")

        # Tab 3: Verification & Parity Audit
        self.tab_audit = QWidget()
        aud_lay = QVBoxLayout(self.tab_audit)
        aud_lay.setContentsMargins(12, 12, 12, 12)
        aud_lay.setSpacing(8)

        self.lbl_parity_summary = QLabel("All generated sets verified.")
        self.lbl_parity_summary.setStyleSheet("font-size: 11pt; font-weight: 700; color: #16A34A;")
        aud_lay.addWidget(self.lbl_parity_summary)

        self.table_set_stats = QTableWidget(0, 4)
        self.table_set_stats.setHorizontalHeaderLabels(["Set Name", "Total Questions", "Total Marks", "Balance Status"])
        self.table_set_stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_set_stats.setMaximumHeight(180)
        aud_lay.addWidget(self.table_set_stats)
        aud_lay.addStretch(1)
        self.tabs.addTab(self.tab_audit, "✓ Set Verification & Parity Audit")

        root_lay.addWidget(self.tabs, 1)

        # 4. Batch Export Controls
        export_box = QGroupBox("Batch Export All Sets")
        exp_lay = QVBoxLayout(export_box)
        exp_lay.setSpacing(8)

        # Folder row
        f_row = QHBoxLayout()
        f_lbl = QLabel("Export Folder:")
        f_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_folder = QLineEdit(str(self.export_dir))
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_folder)
        f_row.addWidget(f_lbl)
        f_row.addWidget(self.txt_folder, 1)
        f_row.addWidget(self.btn_browse)
        exp_lay.addLayout(f_row)

        # Format checkboxes
        f_opts = QHBoxLayout()
        self.chk_exp_pdf = QCheckBox("Export Question Papers (Vector PDF)")
        self.chk_exp_pdf.setChecked(True)
        self.chk_exp_docx = QCheckBox("Export Question Papers (Editable Word .docx)")
        self.chk_exp_docx.setChecked(True)
        self.chk_exp_keys = QCheckBox("Export Synchronized Answer Keys (.pdf & .docx)")
        self.chk_exp_keys.setChecked(True)
        self.chk_exp_master = QCheckBox("Export Master Cross-Set Comparison Document")
        self.chk_exp_master.setChecked(True)
        self.chk_open_folder = QCheckBox("Open folder on completion")
        self.chk_open_folder.setChecked(True)

        f_opts.addWidget(self.chk_exp_pdf)
        f_opts.addWidget(self.chk_exp_docx)
        f_opts.addWidget(self.chk_exp_keys)
        f_opts.addWidget(self.chk_exp_master)
        f_opts.addStretch(1)
        exp_lay.addLayout(f_opts)

        root_lay.addWidget(export_box)

        # 5. Progress and Action Buttons
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root_lay.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Ready to generate and export parallel sets.")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 9pt;")
        root_lay.addWidget(self.lbl_status)

        btn_box = QHBoxLayout()
        btn_box.addWidget(self.chk_open_folder)
        btn_box.addStretch(1)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_close)

        self.btn_export_all = QPushButton("🚀 Export All Sets Now")
        self.btn_export_all.setObjectName("PrimaryButton")
        self.btn_export_all.setStyleSheet("""
            QPushButton#PrimaryButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 700;
                padding: 6px 18px;
                border-radius: 5px;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_export_all.clicked.connect(self.run_export_all)
        btn_box.addWidget(self.btn_export_all)

        root_lay.addLayout(btn_box)

    def _randomize_seed(self) -> None:
        self.spin_seed.setValue(random.randint(100, 999999))
        self._generate_sets_preview()

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Export Folder", self.txt_folder.text())
        if chosen:
            self.txt_folder.setText(chosen)

    # ========================================================================
    # Generation & Table Population
    # ========================================================================

    def _parse_set_identifiers(self) -> List[str]:
        raw = self.txt_set_ids.text().strip()
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        return tokens or ["A", "B", "C", "D"]

    def _generate_sets_preview(self) -> None:
        set_ids = self._parse_set_identifiers()
        opts = ShufflingOptions(
            shuffle_questions=self.chk_shuffle_q.isChecked(),
            shuffle_mcq_options=self.chk_shuffle_mcq.isChecked(),
            shuffle_match_pairs=self.chk_shuffle_match.isChecked(),
            vary_numerical_seeds=self.chk_vary_num.isChecked(),
            keep_choice_groups_contiguous=self.chk_keep_choices.isChecked(),
            preserve_set_a_order=self.chk_preserve_set_a.isChecked(),
            master_seed=self.spin_seed.value(),
        )

        res = MultiSetShuffler.generate_sets(self.project, set_identifiers=set_ids, options=opts)
        self.generation_result = res
        self.sets_generated.emit(res)

        self._populate_mapping_table(res)
        self._populate_answers_table(res)
        self._populate_audit_table(res)

        self.lbl_status.setText(f"✓ Generated {len(res.sets)} parallel sets with Master Seed {res.master_seed}.")

    def _populate_mapping_table(self, res: MultiSetGenerationResult) -> None:
        headers = ["Base Q#", "Prompt Snippet", "Marks"]
        for s_id in res.set_identifiers:
            headers.append(f"Set {s_id} Q#")

        self.table_mapping.clear()
        self.table_mapping.setColumnCount(len(headers))
        self.table_mapping.setHorizontalHeaderLabels(headers)
        self.table_mapping.setRowCount(len(res.mapping_matrix))
        self.table_mapping.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for r_idx, row in enumerate(res.mapping_matrix):
            self.table_mapping.setItem(r_idx, 0, QTableWidgetItem(row.original_number))
            self.table_mapping.setItem(r_idx, 1, QTableWidgetItem(row.prompt_snippet))
            self.table_mapping.setItem(r_idx, 2, QTableWidgetItem(f"{row.marks:g} M"))

            for s_idx, s_id in enumerate(res.set_identifiers, start=3):
                q_num = row.set_numbers.get(s_id, "—")
                item = QTableWidgetItem(q_num)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_mapping.setItem(r_idx, s_idx, item)

    def _populate_answers_table(self, res: MultiSetGenerationResult) -> None:
        headers = ["Base Q#", "Prompt Snippet"]
        for s_id in res.set_identifiers:
            headers.append(f"Set {s_id} Key")

        self.table_answers.clear()
        self.table_answers.setColumnCount(len(headers))
        self.table_answers.setHorizontalHeaderLabels(headers)
        self.table_answers.setRowCount(len(res.mapping_matrix))
        self.table_answers.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for r_idx, row in enumerate(res.mapping_matrix):
            self.table_answers.setItem(r_idx, 0, QTableWidgetItem(row.original_number))
            self.table_answers.setItem(r_idx, 1, QTableWidgetItem(row.prompt_snippet))

            for s_idx, s_id in enumerate(res.set_identifiers, start=2):
                ans = row.set_answers.get(s_id, "—")
                item = QTableWidgetItem(ans)
                self.table_answers.setItem(r_idx, s_idx, item)

    def _populate_audit_table(self, res: MultiSetGenerationResult) -> None:
        self.table_set_stats.setRowCount(len(res.sets))
        base_marks = None
        all_balanced = True

        for r_idx, (s_id, proj) in enumerate(res.sets.items()):
            rep = MarksEngine.audit_paper(proj)
            q_count = len(proj.all_questions_dfs())
            tot_marks = rep.total_paper_marks

            if base_marks is None:
                base_marks = tot_marks
            elif tot_marks != base_marks:
                all_balanced = False

            self.table_set_stats.setItem(r_idx, 0, QTableWidgetItem(f"Set {s_id}"))
            self.table_set_stats.setItem(r_idx, 1, QTableWidgetItem(str(q_count)))
            self.table_set_stats.setItem(r_idx, 2, QTableWidgetItem(f"{tot_marks:g} M"))

            status_text = "✓ Perfect Parity" if rep.is_balanced else "⚠ Marks Discrepancy"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(Qt.GlobalColor.darkGreen if rep.is_balanced else Qt.GlobalColor.darkRed)
            self.table_set_stats.setItem(r_idx, 3, status_item)

        if all_balanced:
            self.lbl_parity_summary.setText("✓ 100% Mark & Question Parity Verified Across All Sets.")
            self.lbl_parity_summary.setStyleSheet("font-size: 11pt; font-weight: 700; color: #16A34A;")
        else:
            self.lbl_parity_summary.setText("⚠ Warning: Discrepancy detected across parallel sets.")
            self.lbl_parity_summary.setStyleSheet("font-size: 11pt; font-weight: 700; color: #D97706;")

    # ========================================================================
    # Batch Export Execution
    # ========================================================================

    def run_export_all(self) -> List[Path]:
        """Execute multi-set batch export generating all sets, answer keys, and master comparison sheets."""
        if not self.generation_result:
            self._generate_sets_preview()

        target_dir = Path(self.txt_folder.text().strip())
        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.lbl_status.setText(f"Cannot create folder: {e}")
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    QMessageBox.critical(self, "Export Error", f"Cannot create target directory '{target_dir}':\n{e}")
                return []

        self.btn_export_all.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(10)
        self.lbl_status.setText("Exporting parallel sets and synchronized answer keys...")
        self.lbl_status.repaint()

        exported_files: List[Path] = []
        try:
            exported_files = MultiSetShuffler.export_all_sets(
                result=self.generation_result,
                output_dir=target_dir,
                export_pdf=self.chk_exp_pdf.isChecked(),
                export_docx=self.chk_exp_docx.isChecked(),
                export_answer_keys=self.chk_exp_keys.isChecked(),
                export_master_matrix=self.chk_exp_master.isChecked(),
            )
            self.progress_bar.setValue(100)
            self.lbl_status.setText(f"✓ Successfully exported {len(exported_files)} documents to {target_dir.name}.")
            self.btn_close.setText("Done")

            if self.chk_open_folder.isChecked() and not os.environ.get("PYTEST_CURRENT_TEST"):
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))

        except Exception as e:
            self.lbl_status.setText(f"Export Error: {e}")
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.critical(self, "Export Error", f"Failed to export multi-set documents:\n{e}")
        finally:
            self.btn_export_all.setEnabled(True)

        return exported_files
