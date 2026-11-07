"""Question Bank Drawer & Reusable Question Library Dialog for Question Paper Studio.

Integrates with SQLiteQuestionBank + FTS5 full-text search:
- Search by keywords, subject, unit, chapter, topic, difficulty, bloom level, question type.
- Preview question prompt, mathematical equations, option layouts, and model answers.
- Insert question into active paper (at currently selected section or node).
- Save active question from paper into the persistent question bank with metadata and tags.
- Revision history viewer with one-click restore.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import BloomLevel, DifficultyLevel, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.storage.sqlite_bank import (
    BankQuestionRecord,
    BankSearchFilter,
    QuestionRevisionEntry,
    SQLiteQuestionBank,
)


class RevisionHistoryDialog(QDialog):
    """Sub-dialog displaying historical revisions of a question in the bank with restore action."""

    revision_restored = Signal(object)  # BankQuestionRecord

    def __init__(
        self,
        bank: SQLiteQuestionBank,
        bank_item_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bank: SQLiteQuestionBank = bank
        self.bank_item_id: str = bank_item_id

        self.setWindowTitle("Question Revision History & Audit Trail")
        self.setMinimumWidth(650)
        self.setMinimumHeight(420)

        self._build_ui()
        self._load_revisions()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        lbl = QLabel("Historical revisions stored in SQLite Question Bank:")
        lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        lay.addWidget(lbl)

        self.table_revs = QTableWidget(0, 4)
        self.table_revs.setHorizontalHeaderLabels(["Version", "Timestamp (UTC)", "Change Note", "Action"])
        self.table_revs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_revs.setAlternatingRowColors(True)
        lay.addWidget(self.table_revs, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        lay.addLayout(btn_box)

    def _load_revisions(self) -> None:
        revs = self.bank.get_revision_history(self.bank_item_id)
        self.table_revs.setRowCount(len(revs))
        for r_idx, rev in enumerate(revs):
            self.table_revs.setItem(r_idx, 0, QTableWidgetItem(f"v{rev.version_number}"))
            self.table_revs.setItem(r_idx, 1, QTableWidgetItem(rev.created_at[:19].replace("T", " ")))
            self.table_revs.setItem(r_idx, 2, QTableWidgetItem(rev.change_note or "—"))

            btn_restore = QPushButton("Restore v" + str(rev.version_number))
            btn_restore.setStyleSheet("color: #2563EB; font-weight: 600;")
            btn_restore.clicked.connect(lambda checked=False, v=rev.version_number: self._on_restore(v))
            self.table_revs.setCellWidget(r_idx, 3, btn_restore)

    def _on_restore(self, version: int) -> None:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            ans = QMessageBox.question(
                self,
                "Confirm Restore",
                f"Restore version {version} as the current question definition in the bank?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        rec = self.bank.restore_revision(self.bank_item_id, version)
        self.revision_restored.emit(rec)
        self.accept()


class QuestionBankDrawer(QDialog):
    """Full-featured Question Bank browser, searcher, and injector dialog."""

    question_inserted = Signal(object, str)  # (QuestionNode, section_id)
    question_saved = Signal(object)          # BankQuestionRecord

    def __init__(
        self,
        bank: SQLiteQuestionBank,
        project: Optional[ProjectState] = None,
        active_question: Optional[QuestionNode] = None,
        target_section_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bank: SQLiteQuestionBank = bank
        self.project: Optional[ProjectState] = project
        self.active_question: Optional[QuestionNode] = active_question
        self.target_section_id: Optional[str] = target_section_id
        self.selected_record: Optional[BankQuestionRecord] = None

        self.setWindowTitle("📚 Question Bank & Reusable Asset Library")
        self.setMinimumWidth(920)
        self.setMinimumHeight(620)

        self._build_ui()
        self._on_search()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(14, 14, 14, 14)
        root_lay.setSpacing(10)

        # 1. Search Bar & Filters
        search_box = QGroupBox("Search & Filter Question Bank (FTS5 Full-Text Engine)")
        s_lay = QVBoxLayout(search_box)
        s_lay.setSpacing(8)

        # Top search row
        top_row = QHBoxLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("Search questions by keywords, concepts, or formulas (FTS5)...")
        self.txt_query.returnPressed.connect(self._on_search)
        self.btn_search = QPushButton("🔍 Search")
        self.btn_search.clicked.connect(self._on_search)
        top_row.addWidget(self.txt_query, 1)
        top_row.addWidget(self.btn_search)
        s_lay.addLayout(top_row)

        # Filter combos row
        filter_row = QHBoxLayout()
        self.combo_type = QComboBox()
        self.combo_type.addItem("All Question Types", None)
        for qt in QuestionType:
            self.combo_type.addItem(qt.value.replace("_", " ").title(), qt)
        self.combo_type.currentIndexChanged.connect(self._on_search)

        self.combo_diff = QComboBox()
        self.combo_diff.addItem("All Difficulties", None)
        for d in DifficultyLevel:
            self.combo_diff.addItem(d.value.title(), d)
        self.combo_diff.currentIndexChanged.connect(self._on_search)

        self.combo_bloom = QComboBox()
        self.combo_bloom.addItem("All Bloom Levels", None)
        for b in BloomLevel:
            self.combo_bloom.addItem(b.value.title(), b)
        self.combo_bloom.currentIndexChanged.connect(self._on_search)

        self.btn_reset_filters = QPushButton("Reset Filters")
        self.btn_reset_filters.clicked.connect(self._reset_filters)

        filter_row.addWidget(QLabel("Type:"))
        filter_row.addWidget(self.combo_type)
        filter_row.addSpacing(10)
        filter_row.addWidget(QLabel("Difficulty:"))
        filter_row.addWidget(self.combo_diff)
        filter_row.addSpacing(10)
        filter_row.addWidget(QLabel("Bloom:"))
        filter_row.addWidget(self.combo_bloom)
        filter_row.addSpacing(10)
        filter_row.addWidget(self.btn_reset_filters)
        filter_row.addStretch(1)
        s_lay.addLayout(filter_row)

        root_lay.addWidget(search_box)

        # 2. Main 2-Pane Splitter (Results List + Question Preview)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left list: search results
        list_frame = QFrame()
        l_lay = QVBoxLayout(list_frame)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(4)

        self.lbl_result_count = QLabel("Results: 0 question(s)")
        self.lbl_result_count.setStyleSheet("font-weight: 600; color: #475569;")
        l_lay.addWidget(self.lbl_result_count)

        self.table_results = QTableWidget(0, 4)
        self.table_results.setHorizontalHeaderLabels(["Question", "Type", "Marks", "Used"])
        self.table_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_results.setAlternatingRowColors(True)
        self.table_results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_results.itemSelectionChanged.connect(self._on_selection_changed)
        l_lay.addWidget(self.table_results, 1)

        splitter.addWidget(list_frame)

        # Right pane: question details & preview
        preview_frame = QFrame()
        preview_frame.setStyleSheet("background-color: #FAFAFA; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        p_lay = QVBoxLayout(preview_frame)
        p_lay.setContentsMargins(8, 8, 8, 8)
        p_lay.setSpacing(6)

        self.lbl_preview_header = QLabel("Question Preview")
        self.lbl_preview_header.setStyleSheet("font-size: 11pt; font-weight: 700; color: #1E293B;")
        p_lay.addWidget(self.lbl_preview_header)

        self.lbl_preview_meta = QLabel("Select a question to inspect details.")
        self.lbl_preview_meta.setStyleSheet("color: #64748B; font-size: 9pt;")
        p_lay.addWidget(self.lbl_preview_meta)

        self.browser_preview = QTextBrowser()
        self.browser_preview.setStyleSheet("background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px;")
        p_lay.addWidget(self.browser_preview, 1)

        # Action buttons on preview pane
        act_row = QHBoxLayout()
        self.btn_insert = QPushButton("📥 Insert into Paper")
        self.btn_insert.setEnabled(False)
        self.btn_insert.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 700;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
            QPushButton:disabled { background-color: #94A3B8; }
        """)
        self.btn_insert.clicked.connect(self._on_insert_into_paper)

        self.btn_history = QPushButton("📜 Revisions...")
        self.btn_history.setEnabled(False)
        self.btn_history.clicked.connect(self._on_view_revisions)

        act_row.addWidget(self.btn_insert)
        act_row.addWidget(self.btn_history)
        act_row.addStretch(1)
        p_lay.addLayout(act_row)

        splitter.addWidget(preview_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root_lay.addWidget(splitter, 1)

        # 3. Bottom Action Strip (Save active question to bank + Close)
        bot_bar = QHBoxLayout()

        if self.active_question is not None:
            self.btn_save_current = QPushButton("💾 Save Active Question from Paper into Bank")
            self.btn_save_current.setStyleSheet("color: #059669; font-weight: 600; padding: 6px;")
            self.btn_save_current.clicked.connect(self._on_save_active_question)
            bot_bar.addWidget(self.btn_save_current)

        bot_bar.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bot_bar.addWidget(btn_close)

        root_lay.addLayout(bot_bar)

    def _reset_filters(self) -> None:
        self.txt_query.clear()
        self.combo_type.setCurrentIndex(0)
        self.combo_diff.setCurrentIndex(0)
        self.combo_bloom.setCurrentIndex(0)
        self._on_search()

    def _on_search(self) -> None:
        query = self.txt_query.text().strip()
        q_type = self.combo_type.currentData()
        diff = self.combo_diff.currentData()
        bloom = self.combo_bloom.currentData()

        filt = BankSearchFilter(
            query_text=query,
            question_type=q_type,
            difficulty=diff,
            bloom_level=bloom,
            limit=100,
        )
        self.current_records: List[BankQuestionRecord] = self.bank.search(filt)
        self.lbl_result_count.setText(f"Found {len(self.current_records)} matching question(s)")

        self.table_results.setRowCount(len(self.current_records))
        for r_idx, rec in enumerate(self.current_records):
            clean_text = rec.plain_text[:60] + ("..." if len(rec.plain_text) > 60 else "")
            self.table_results.setItem(r_idx, 0, QTableWidgetItem(clean_text or "[Empty Question]"))
            self.table_results.setItem(r_idx, 1, QTableWidgetItem(rec.question.question_type.value))

            m_val = rec.question.marks if rec.question.marks is not None else 0.0
            self.table_results.setItem(r_idx, 2, QTableWidgetItem(f"{m_val:g} M"))
            self.table_results.setItem(r_idx, 3, QTableWidgetItem(str(rec.usage_count)))

        if self.current_records:
            self.table_results.selectRow(0)
            self._on_selection_changed()
        else:
            self.selected_record = None
            self.btn_insert.setEnabled(False)
            self.btn_history.setEnabled(False)
            self.browser_preview.setHtml("<p style='color:#64748B;'>No questions match the current filter.</p>")

    def _on_selection_changed(self) -> None:
        row = self.table_results.currentRow()
        if row < 0 or row >= len(getattr(self, "current_records", [])):
            return

        rec = self.current_records[row]
        self.selected_record = rec
        self.btn_insert.setEnabled(True)
        self.btn_history.setEnabled(True)

        self.lbl_preview_header.setText(f"Question Preview — {rec.question.question_type.value}")
        tags_str = ", ".join(rec.tags) if rec.tags else "None"
        diff_str = rec.difficulty or "Normal"
        bloom_str = rec.bloom_level or "Unassigned"
        self.lbl_preview_meta.setText(f"Diff: {diff_str} | Bloom: {bloom_str} | Tags: {tags_str} | Version: v{rec.current_version}")

        # Render preview HTML
        preview_body = f"""
        <div style="font-family: sans-serif; font-size: 10pt; line-height: 1.5;">
            <p><b>Prompt:</b></p>
            <div style="margin-left: 8px;">{rec.question.prompt_html or '<i>[Empty prompt]</i>'}</div>
        """
        if rec.question.marking_scheme and rec.question.marking_scheme.model_answer_html:
            preview_body += f"""
            <hr style="border: 0; border-top: 1px dashed #CBD5E1; margin: 12px 0;">
            <p style="color: #059669;"><b>Model Answer / Solution:</b></p>
            <div style="margin-left: 8px;">{rec.question.marking_scheme.model_answer_html}</div>
            """
        preview_body += "</div>"
        self.browser_preview.setHtml(preview_body)

    def _on_insert_into_paper(self) -> None:
        if not self.selected_record:
            return

        cloned_node = self.selected_record.question.clone_with_new_ids()
        # Record usage in the SQLite bank
        self.bank.record_usage(
            self.selected_record.bank_item_id,
            project_id=self.project.project_id if self.project else "unknown",
            exam_title=self.project.title if self.project else "Paper Setter",
        )

        target_sec = self.target_section_id
        if not target_sec and self.project and self.project.sections:
            target_sec = self.project.sections[0].section_id

        self.question_inserted.emit(cloned_node, target_sec or "")
        self.accept()

    def _on_view_revisions(self) -> Optional[RevisionHistoryDialog]:
        if not self.selected_record:
            return None
        dlg = RevisionHistoryDialog(self.bank, self.selected_record.bank_item_id, parent=self)
        dlg.revision_restored.connect(lambda rec: self._on_search())
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            dlg.exec()
        return dlg

    def _on_save_active_question(self) -> Optional[BankQuestionRecord]:
        if not self.active_question:
            return None

        from src.core.models.question_model import TaxonomyMetadata

        q_to_save = self.active_question.model_copy(deep=True)
        subject = (self.project.exam_metadata.subject_name if self.project else "General") or "General"
        if q_to_save.taxonomy_metadata is None:
            q_to_save.taxonomy_metadata = TaxonomyMetadata(
                subject=subject,
                tags=["Paper Export", subject],
            )
        else:
            if not q_to_save.taxonomy_metadata.subject:
                q_to_save.taxonomy_metadata.subject = subject
            if subject not in q_to_save.taxonomy_metadata.tags:
                q_to_save.taxonomy_metadata.tags.append(subject)

        item_id = self.bank.add_question(question=q_to_save)
        rec = self.bank.get_record(item_id)
        if rec:
            self.question_saved.emit(rec)
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.information(
                    self,
                    "Saved to Question Bank",
                    f"Question successfully saved to Question Bank with ID '{rec.bank_item_id[:8]}...'",
                )
        self._on_search()
        return rec
