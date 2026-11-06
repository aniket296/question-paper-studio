"""Dialogs and management widgets for Internal Choice Groups and Shared Reading Passages."""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import ChoiceRuleType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import ChoiceGroup, Section, SharedPassage
from src.ui.workspace.rich_text_editor import RichTextEditor


class ChoiceGroupManagerDialog(QDialog):
    """Dialog for managing internal choice groups (OR choice pairs and Any K of N) within a Section."""

    groups_changed = Signal()

    def __init__(
        self,
        section: Section,
        project: ProjectState,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.section: Section = section
        self.project: ProjectState = project

        self.setWindowTitle(f"Internal Choice Groups — {section.title}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_desc = QLabel(
            "Configure internal choices (e.g. 'Question 4 OR Question 5', or 'Answer any 3 out of 5 questions')."
        )
        lbl_desc.setStyleSheet("color: #64748B; font-size: 9.5pt;")
        layout.addWidget(lbl_desc)

        # 1. Existing choice groups table
        self.table_groups = QTableWidget(0, 4)
        self.table_groups.setHorizontalHeaderLabels(["Rule Type", "Attempt Rule", "Linked Questions", "Action"])
        self.table_groups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_groups.setAlternatingRowColors(True)
        layout.addWidget(self.table_groups, 1)

        # 2. Add New Choice Group Section
        add_box = QGroupBox("+ Create New Choice Group")
        add_lay = QVBoxLayout(add_box)
        add_lay.setSpacing(8)

        # Rule type selector
        r_row = QHBoxLayout()
        r_lbl = QLabel("Rule Type:")
        r_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.combo_rule = QComboBox()
        self.combo_rule.addItem("OR Choice Pair (Attempt 1 of 2)", ChoiceRuleType.OR_PAIR)
        self.combo_rule.addItem("Answer Any K of N", ChoiceRuleType.ANY_K_OF_N)
        self.combo_rule.currentIndexChanged.connect(self._on_rule_type_changed)
        r_row.addWidget(r_lbl)
        r_row.addWidget(self.combo_rule)

        self.k_lbl = QLabel("Required K:")
        self.k_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.k_lbl.setVisible(False)
        self.spin_k = QSpinBox()
        self.spin_k.setRange(1, 20)
        self.spin_k.setValue(2)
        self.spin_k.setVisible(False)
        r_row.addWidget(self.k_lbl)
        r_row.addWidget(self.spin_k)
        r_row.addStretch(1)
        add_lay.addLayout(r_row)

        # Question checkboxes list
        q_lbl = QLabel("Select questions in this section to include in this choice group:")
        q_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        add_lay.addWidget(q_lbl)

        self.list_questions = QListWidget()
        self.list_questions.setMaximumHeight(130)
        for q in self.section.questions:
            item = QListWidgetItem(f"{q.resolved_number or '•'} ({q.question_type.value}) {q.prompt_html[:50]}")
            item.setData(Qt.ItemDataRole.UserRole, q.question_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_questions.addItem(item)
        add_lay.addWidget(self.list_questions)

        self.btn_create_group = QPushButton("Create Choice Group")
        self.btn_create_group.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: 700; padding: 6px;")
        self.btn_create_group.clicked.connect(self._on_create_group)
        add_lay.addWidget(self.btn_create_group)

        layout.addWidget(add_box)

        # 3. Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_close = QPushButton("Done")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _on_rule_type_changed(self) -> None:
        rule = self.combo_rule.currentData()
        is_k_of_n = rule == ChoiceRuleType.ANY_K_OF_N
        self.k_lbl.setVisible(is_k_of_n)
        self.spin_k.setVisible(is_k_of_n)

    def _refresh_list(self) -> None:
        self.table_groups.setRowCount(0)
        q_map = {q.question_id: q for q in self.section.questions}

        for idx, grp in enumerate(self.section.choice_groups):
            row = self.table_groups.rowCount()
            self.table_groups.insertRow(row)

            rule_name = "OR Choice Pair" if grp.rule_type == ChoiceRuleType.OR_PAIR else "Any K of N"
            self.table_groups.setItem(row, 0, QTableWidgetItem(rule_name))

            k_text = "Attempt 1" if grp.rule_type == ChoiceRuleType.OR_PAIR else f"Attempt {grp.attempt_count_k} of {len(grp.question_ids)}"
            self.table_groups.setItem(row, 1, QTableWidgetItem(k_text))

            labels = []
            for qid in grp.question_ids:
                if qid in q_map:
                    labels.append(q_map[qid].resolved_number or "•")
            linked_text = " OR ".join(labels) if grp.rule_type == ChoiceRuleType.OR_PAIR else ", ".join(labels)
            self.table_groups.setItem(row, 2, QTableWidgetItem(linked_text))

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet("color: #DC2626;")
            btn_del.clicked.connect(lambda checked=False, g_id=grp.choice_group_id: self._on_delete_group(g_id))
            self.table_groups.setCellWidget(row, 3, btn_del)

    def _on_create_group(self) -> None:
        rule = self.combo_rule.currentData()
        selected_qids = []
        for i in range(self.list_questions.count()):
            item = self.list_questions.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_qids.append(item.data(Qt.ItemDataRole.UserRole))

        if rule == ChoiceRuleType.OR_PAIR and len(selected_qids) != 2:
            QMessageBox.warning(self, "Invalid Selection", "Please check exactly 2 questions to form an OR Choice Pair.")
            return
        elif rule == ChoiceRuleType.ANY_K_OF_N and len(selected_qids) < 2:
            QMessageBox.warning(self, "Invalid Selection", "Please check at least 2 questions for an Any K of N group.")
            return

        k_val = 1 if rule == ChoiceRuleType.OR_PAIR else self.spin_k.value()
        if k_val >= len(selected_qids):
            QMessageBox.warning(self, "Invalid K Value", f"K ({k_val}) must be strictly less than total selected questions ({len(selected_qids)}).")
            return

        new_grp = ChoiceGroup(
            choice_group_id=str(uuid4()),
            rule_type=rule,
            question_ids=selected_qids,
            attempt_count_k=k_val,
        )
        self.section.choice_groups.append(new_grp)

        # Update questions
        for q in self.section.questions:
            if q.question_id in selected_qids:
                q.choice_group_id = new_grp.choice_group_id

        # Reset checks
        for i in range(self.list_questions.count()):
            self.list_questions.item(i).setCheckState(Qt.CheckState.Unchecked)

        self._refresh_list()
        self.groups_changed.emit()

    def _on_delete_group(self, group_id: str) -> None:
        self.section.choice_groups = [g for g in self.section.choice_groups if g.choice_group_id != group_id]
        for q in self.section.questions:
            if q.choice_group_id == group_id:
                q.choice_group_id = None
        self._refresh_list()
        self.groups_changed.emit()


class SharedPassageDialog(QDialog):
    """Dialog for creating or editing a shared reading passage / stimulus across questions."""

    passage_saved = Signal(object)  # SharedPassage

    def __init__(
        self,
        section: Section,
        passage: Optional[SharedPassage] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.section: Section = section
        self.passage: SharedPassage = passage or SharedPassage()
        self.is_new: bool = passage is None

        self.setWindowTitle("Shared Reading Passage / Stimulus")
        self.setMinimumWidth(640)
        self.setMinimumHeight(500)

        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title row
        t_row = QHBoxLayout()
        t_lbl = QLabel("Passage Title:")
        t_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. Reading Comprehension: Renewable Energy Transitions")
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.txt_title, 1)
        layout.addLayout(t_row)

        # Instruction row
        i_row = QHBoxLayout()
        i_lbl = QLabel("Instructions:")
        i_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_instruction = QLineEdit()
        self.txt_instruction.setText("Read the following passage carefully and answer the questions that follow:")
        i_row.addWidget(i_lbl)
        i_row.addWidget(self.txt_instruction, 1)
        layout.addLayout(i_row)

        # Passage Content Editor
        c_lbl = QLabel("Passage Body / Stimulus Text:")
        c_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        layout.addWidget(c_lbl)

        self.editor_content = RichTextEditor(placeholder="Enter comprehension passage, table, or context...", parent=self)
        layout.addWidget(self.editor_content, 1)

        # Linked questions selection
        q_box = QGroupBox("Link Passage to Questions in this Section")
        q_lay = QVBoxLayout(q_box)
        self.list_questions = QListWidget()
        self.list_questions.setMaximumHeight(120)
        for q in self.section.questions:
            item = QListWidgetItem(f"{q.resolved_number or '•'} ({q.question_type.value}) {q.prompt_html[:50]}")
            item.setData(Qt.ItemDataRole.UserRole, q.question_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_questions.addItem(item)
        q_lay.addWidget(self.list_questions)
        layout.addWidget(q_box)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Save Passage")
        btn_save.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: 700; padding: 6px 14px;")
        btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_data(self) -> None:
        self.txt_title.setText(self.passage.title)
        if self.passage.instruction_text:
            self.txt_instruction.setText(self.passage.instruction_text)
        self.editor_content.set_html(self.passage.content_html)

        linked_set = set(self.passage.linked_question_ids)
        for i in range(self.list_questions.count()):
            item = self.list_questions.item(i)
            qid = item.data(Qt.ItemDataRole.UserRole)
            if qid in linked_set:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_save(self) -> None:
        self.passage.title = self.txt_title.text().strip()
        self.passage.instruction_text = self.txt_instruction.text().strip()
        self.passage.content_html = self.editor_content.get_html()

        selected_qids = []
        for i in range(self.list_questions.count()):
            item = self.list_questions.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_qids.append(item.data(Qt.ItemDataRole.UserRole))

        self.passage.linked_question_ids = selected_qids

        # Update question nodes
        for q in self.section.questions:
            if q.question_id in selected_qids:
                q.shared_passage_id = self.passage.passage_id
            elif q.shared_passage_id == self.passage.passage_id:
                q.shared_passage_id = None

        if self.is_new:
            self.section.shared_passages.append(self.passage)

        self.passage_saved.emit(self.passage)
        self.accept()
