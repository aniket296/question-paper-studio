"""Hierarchical Question Paper Outline Tree with Drag-and-Drop, Numbering & Marks Badges."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.marks_engine import MarksEngine
from src.core.engine.numbering_fsm import NumberingFSM, QuestionTreeEngine
from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import Section

ITEM_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1      # "section" or "question"
ITEM_ROLE_ID = Qt.ItemDataRole.UserRole + 2        # section_id or question_id


class OutlineTreeWidget(QWidget):
    """Hierarchical tree representation of question paper sections, questions, and sub-questions."""

    question_selected = Signal(str)      # question_id
    section_selected = Signal(str)       # section_id
    tree_structure_changed = Signal(str) # change description for Undo/Redo tracking

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[ProjectState] = None
        self._block_signals = False

        self._build_ui()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(4)

        # 1. Top Action Toolbar
        action_bar = QFrame()
        action_bar.setObjectName("CardFrame")
        action_bar.setStyleSheet("#CardFrame { background-color: #F8FAFC; border-bottom: 1px solid #E2E8F0; padding: 4px; }")
        ab_lay = QHBoxLayout(action_bar)
        ab_lay.setContentsMargins(6, 4, 6, 4)
        ab_lay.setSpacing(4)

        self.btn_add_section = QPushButton("+ Section")
        self.btn_add_section.setToolTip("Add new examination section")
        self.btn_add_section.clicked.connect(self.on_add_section)
        ab_lay.addWidget(self.btn_add_section)

        self.btn_add_question = QPushButton("+ Question")
        self.btn_add_question.setObjectName("PrimaryButton")
        self.btn_add_question.setToolTip("Add new top-level question")
        self.btn_add_question.clicked.connect(self.on_add_question)
        ab_lay.addWidget(self.btn_add_question)

        self.btn_add_sub_q = QPushButton("+ Sub-Q")
        self.btn_add_sub_q.setToolTip("Add child sub-question to selected question")
        self.btn_add_sub_q.clicked.connect(self.on_add_sub_question)
        ab_lay.addWidget(self.btn_add_sub_q)

        ab_lay.addStretch(1)

        self.btn_up = QPushButton("▲")
        self.btn_up.setMaximumWidth(28)
        self.btn_up.setToolTip("Move question up")
        self.btn_up.clicked.connect(self.on_move_up)
        ab_lay.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼")
        self.btn_down.setMaximumWidth(28)
        self.btn_down.setToolTip("Move question down")
        self.btn_down.clicked.connect(self.on_move_down)
        ab_lay.addWidget(self.btn_down)

        self.btn_duplicate = QPushButton("⎘")
        self.btn_duplicate.setMaximumWidth(28)
        self.btn_duplicate.setToolTip("Duplicate selected question")
        self.btn_duplicate.clicked.connect(self.on_duplicate)
        ab_lay.addWidget(self.btn_duplicate)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setMaximumWidth(28)
        self.btn_delete.setToolTip("Delete selected question or section")
        self.btn_delete.clicked.connect(self.on_delete)
        ab_lay.addWidget(self.btn_delete)

        root_lay.addWidget(action_bar)

        # 2. Tree Widget
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Question / Section", "Marks", "Type"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAlternatingRowColors(True)
        self.tree.setAnimated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemSelectionChanged.connect(self._on_item_selection_changed)

        root_lay.addWidget(self.tree, 1)

    def load_project(
        self,
        project: ProjectState,
        select_question_id: Optional[str] = None,
    ) -> None:
        """Populate tree nodes from `project` sections and questions."""
        self.project = project
        self._block_signals = True
        try:
            self.tree.clear()
            if not project.sections:
                return

            labels = NumberingFSM.resolve_project(project)
            uses_multi = project.uses_explicit_sections

            selected_item: Optional[QTreeWidgetItem] = None

            for s_idx, section in enumerate(project.sections):
                sec_item: QTreeWidgetItem
                if uses_multi:
                    sec_item = QTreeWidgetItem(self.tree)
                    sec_item.setData(0, ITEM_ROLE_TYPE, "section")
                    sec_item.setData(0, ITEM_ROLE_ID, section.section_id)
                    sec_title = section.title or f"Section {s_idx + 1}"
                    if section.attempt_any_k is not None:
                        sec_title += f" [Attempt any {section.attempt_any_k}]"
                    sec_item.setText(0, f"📁 {sec_title}")
                    font = sec_item.font(0)
                    font.setBold(True)
                    sec_item.setFont(0, font)
                    sec_item.setBackground(0, QColor("#F1F5F9"))
                    sec_item.setBackground(1, QColor("#F1F5F9"))
                    sec_item.setBackground(2, QColor("#F1F5F9"))
                    sec_item.setExpanded(True)
                else:
                    sec_item = self.tree.invisibleRootItem()

                for q in section.questions:
                    item = self._create_question_tree_item(q, labels, sec_item)
                    if select_question_id and q.question_id == select_question_id:
                        selected_item = item

            # Restore selection if requested or default to first question
            if selected_item:
                self.tree.setCurrentItem(selected_item)
            elif self.tree.topLevelItemCount() > 0:
                top = self.tree.topLevelItem(0)
                if top.childCount() > 0:
                    self.tree.setCurrentItem(top.child(0))
                else:
                    self.tree.setCurrentItem(top)
        finally:
            self._block_signals = False

        # Emit selection after population
        self._on_item_selection_changed()

    def _create_question_tree_item(
        self,
        node: QuestionNode,
        labels: Dict[str, str],
        parent_item: QTreeWidgetItem,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent_item)
        item.setData(0, ITEM_ROLE_TYPE, "question")
        item.setData(0, ITEM_ROLE_ID, node.question_id)

        num_label = labels.get(node.question_id, node.resolved_number or "•")
        clean_text = self._strip_html(node.prompt_html or "").strip()
        snippet = clean_text[:40] + ("..." if len(clean_text) > 40 else "")

        badges: List[str] = []
        if node.choice_group_id:
            badges.append("[OR]")
        if node.shared_passage_id:
            badges.append("[Passage]")
        if node.prompt_secondary_html and node.prompt_secondary_html.strip():
            badges.append("[🌐]")
        badge_prefix = " ".join(badges) + " " if badges else ""

        display_text = f"{num_label} {badge_prefix}{snippet}" if snippet else f"{num_label} {badge_prefix}[Empty]"
        item.setText(0, display_text)

        # Marks badge
        marks = MarksEngine.calculate_question_effective_marks(node).effective_marks
        marks_str = f"[{int(marks)} M]" if marks.is_integer() else f"[{marks:g} M]"
        item.setText(1, marks_str)
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

        # Type chip
        type_str = self._format_question_type(node.question_type)
        item.setText(2, type_str)
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)

        item.setExpanded(True)

        for child in node.children:
            self._create_question_tree_item(child, labels, item)

        return item

    @staticmethod
    def _strip_html(raw_html: str) -> str:
        return re.sub(r"<[^>]+>", "", raw_html)

    @staticmethod
    def _format_question_type(qtype: QuestionType) -> str:
        mapping = {
            QuestionType.NORMAL: "Normal",
            QuestionType.MCQ: "MCQ",
            QuestionType.FILL_IN_THE_BLANK: "Fill Blank",
            QuestionType.MATCH_THE_PAIR: "Match Pair",
            QuestionType.TRUE_FALSE: "T/F",
            QuestionType.ASSERTION_REASON: "Assert-Reason",
            QuestionType.CASE_BASED: "Case Based",
            QuestionType.SHORT_ANSWER: "Short Ans",
            QuestionType.LONG_ANSWER: "Long Ans",
            QuestionType.NUMERICAL_DYNAMIC: "Numerical",
            QuestionType.ORDERING_SEQUENCING: "Ordering",
            QuestionType.DIAGRAM_LABELLING: "Diagram",
            QuestionType.SOURCE_BASED: "Source",
        }
        return mapping.get(qtype, str(qtype.value))

    # ========================================================================
    # Selection and Querying
    # ========================================================================

    def get_selected_item_info(self) -> tuple[Optional[str], Optional[str]]:
        """Return (item_type, item_id) for the current selection."""
        cur = self.tree.currentItem()
        if not cur:
            return None, None
        itype = cur.data(0, ITEM_ROLE_TYPE)
        iid = cur.data(0, ITEM_ROLE_ID)
        return itype, iid

    def get_selected_question_id(self) -> Optional[str]:
        itype, iid = self.get_selected_item_info()
        return iid if itype == "question" else None

    def get_selected_section_id(self) -> Optional[str]:
        cur = self.tree.currentItem()
        if not cur:
            return self.project.sections[0].section_id if self.project and self.project.sections else None

        itype = cur.data(0, ITEM_ROLE_TYPE)
        iid = cur.data(0, ITEM_ROLE_ID)
        if itype == "section":
            return iid

        # If question is selected, traverse up to find containing section or return node's section_id
        if self.project:
            lookup = QuestionTreeEngine.find_node(self.project, iid)
            if lookup and lookup.section:
                return lookup.section.section_id

        return self.project.sections[0].section_id if self.project and self.project.sections else None

    def select_question(self, question_id: str) -> None:
        """Find and select item corresponding to `question_id`."""
        def _find(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, ITEM_ROLE_ID) == question_id:
                return item
            for i in range(item.childCount()):
                res = _find(item.child(i))
                if res:
                    return res
            return None

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            found = _find(root.child(i))
            if found:
                self.tree.setCurrentItem(found)
                return

    def _on_item_selection_changed(self) -> None:
        if self._block_signals:
            return
        itype, iid = self.get_selected_item_info()
        if itype == "question" and iid:
            self.question_selected.emit(iid)
        elif itype == "section" and iid:
            self.section_selected.emit(iid)

    # ========================================================================
    # Tree Actions & Mutations
    # ========================================================================

    def on_add_question(self) -> None:
        """Add a top-level question to the active section."""
        if not self.project:
            return

        sec_id = self.get_selected_section_id()
        new_q = QuestionTreeEngine.add_parent_question(
            self.project,
            section_id=sec_id,
            question=QuestionNode(prompt_html="<p>New Question</p>", marks=2.0),
        )
        self.load_project(self.project, select_question_id=new_q.question_id)
        self.tree_structure_changed.emit("Add Question")

    def on_add_sub_question(self) -> None:
        """Add a child sub-question beneath the currently selected question."""
        if not self.project:
            return

        qid = self.get_selected_question_id()
        if not qid:
            QMessageBox.information(self, "Add Sub-Question", "Please select a parent question first.")
            return

        new_sub = QuestionTreeEngine.add_child_question(
            self.project,
            parent_question_id=qid,
            child=QuestionNode(prompt_html="<p>Sub-question</p>", marks=1.0),
        )
        self.load_project(self.project, select_question_id=new_sub.question_id)
        self.tree_structure_changed.emit("Add Sub-Question")

    def on_add_section(self) -> None:
        """Add a new section to the question paper."""
        if not self.project:
            return

        title, ok = QInputDialog.getText(
            self,
            "New Section",
            "Enter Section Title (e.g. 'Section B: Short Answer Questions'):",
            text=f"Section {chr(65 + len(self.project.sections))}",
        )
        if not ok or not title.strip():
            return

        # If previous section was the unsectioned transparent default, promote it
        if len(self.project.sections) == 1 and self.project.sections[0].is_default_unsectioned:
            self.project.sections[0].is_default_unsectioned = False
            self.project.sections[0].title = "Section A"

        new_sec = Section(title=title.strip(), is_default_unsectioned=False)
        self.project.sections.append(new_sec)

        # Add initial question to the new section
        QuestionTreeEngine.add_parent_question(
            self.project,
            section_id=new_sec.section_id,
            question=QuestionNode(prompt_html="<p>New Question</p>", marks=2.0),
        )
        self.load_project(self.project)
        self.tree_structure_changed.emit("Add Section")

    def on_move_up(self) -> None:
        """Move the selected question up among its siblings."""
        if not self.project:
            return
        qid = self.get_selected_question_id()
        if not qid:
            return

        moved = QuestionTreeEngine.move_up(self.project, qid)
        if moved:
            self.load_project(self.project, select_question_id=qid)
            self.tree_structure_changed.emit("Move Question Up")

    def on_move_down(self) -> None:
        """Move the selected question down among its siblings."""
        if not self.project:
            return
        qid = self.get_selected_question_id()
        if not qid:
            return

        moved = QuestionTreeEngine.move_down(self.project, qid)
        if moved:
            self.load_project(self.project, select_question_id=qid)
            self.tree_structure_changed.emit("Move Question Down")

    def on_duplicate(self) -> None:
        """Duplicate the selected question and its children."""
        if not self.project:
            return
        qid = self.get_selected_question_id()
        if not qid:
            return

        cloned = QuestionTreeEngine.duplicate_node(self.project, qid)
        self.load_project(self.project, select_question_id=cloned.question_id)
        self.tree_structure_changed.emit("Duplicate Question")

    def on_delete(self) -> None:
        """Delete the selected question or section with child confirmation."""
        if not self.project:
            return

        itype, iid = self.get_selected_item_info()
        if not itype or not iid:
            return

        if itype == "question":
            lookup = QuestionTreeEngine.find_node(self.project, iid)
            if not lookup:
                return

            if lookup.node.children:
                count = QuestionTreeEngine.count_descendants(lookup.node)
                ans = QMessageBox.question(
                    self,
                    "Delete Question with Sub-Questions",
                    f"This question has {count} sub-question(s).\n\n"
                    "Deleting it will delete all its sub-questions. Do you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return

            QuestionTreeEngine.delete_node(self.project, iid, allow_with_children=True)
            self.load_project(self.project)
            self.tree_structure_changed.emit("Delete Question")

        elif itype == "section":
            if len(self.project.sections) <= 1:
                QMessageBox.warning(self, "Cannot Delete Section", "The paper must have at least one section.")
                return

            sec = QuestionTreeEngine.find_section(self.project, iid)
            if not sec:
                return

            q_count = len(sec.questions)
            if q_count > 0:
                ans = QMessageBox.question(
                    self,
                    "Delete Section",
                    f"Section '{sec.title}' contains {q_count} question(s).\n\n"
                    "Delete the section and all its questions?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return

            self.project.sections.remove(sec)
            self.load_project(self.project)
            self.tree_structure_changed.emit("Delete Section")

    # ========================================================================
    # Context Menu
    # ========================================================================

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        itype = item.data(0, ITEM_ROLE_TYPE)
        iid = item.data(0, ITEM_ROLE_ID)

        if itype == "question":
            act_add_q = menu.addAction("+ Add Question Below")
            act_add_q.triggered.connect(self.on_add_question)

            act_add_sub = menu.addAction("+ Add Sub-Question")
            act_add_sub.triggered.connect(self.on_add_sub_question)

            menu.addSeparator()

            act_dup = menu.addAction("⎘ Duplicate Question")
            act_dup.triggered.connect(self.on_duplicate)

            act_del = menu.addAction("✕ Delete Question")
            act_del.triggered.connect(self.on_delete)

            menu.addSeparator()

            act_up = menu.addAction("▲ Move Up")
            act_up.triggered.connect(self.on_move_up)

            act_down = menu.addAction("▼ Move Down")
            act_down.triggered.connect(self.on_move_down)

            menu.addSeparator()

            act_choice = menu.addAction("🔗 Manage Section Choice Groups (OR / K of N)...")
            act_choice.triggered.connect(lambda: self._on_manage_choice_groups(iid))

            act_passage = menu.addAction("📖 Add / Edit Shared Passage...")
            act_passage.triggered.connect(lambda: self._on_manage_shared_passages(iid))

        elif itype == "section":
            act_add_q = menu.addAction("+ Add Question to Section")
            act_add_q.triggered.connect(self.on_add_question)

            menu.addSeparator()

            act_choice_sec = menu.addAction("🔗 Manage Choice Groups (OR / K of N)...")
            act_choice_sec.triggered.connect(lambda: self._on_manage_choice_groups_section(iid))

            act_passage_sec = menu.addAction("📖 Add / Edit Shared Passage...")
            act_passage_sec.triggered.connect(lambda: self._on_manage_shared_passages_section(iid))

            menu.addSeparator()

            act_del_sec = menu.addAction("✕ Delete Section")
            act_del_sec.triggered.connect(self.on_delete)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_manage_choice_groups(self, question_id: str) -> None:
        if not self.project:
            return
        lookup = QuestionTreeEngine.find_node(self.project, question_id)
        if not lookup or not lookup.section:
            return
        self._on_manage_choice_groups_section(lookup.section.section_id)

    def _on_manage_choice_groups_section(self, section_id: str) -> None:
        if not self.project:
            return
        sec = QuestionTreeEngine.find_section(self.project, section_id)
        if not sec:
            return
        from src.ui.workspace.choice_passage_dialog import ChoiceGroupManagerDialog
        dlg = ChoiceGroupManagerDialog(sec, self.project, parent=self)
        dlg.groups_changed.connect(lambda: self.tree_structure_changed.emit("Update Choice Groups"))
        dlg.exec()
        self.load_project(self.project)

    def _on_manage_shared_passages(self, question_id: str) -> None:
        if not self.project:
            return
        lookup = QuestionTreeEngine.find_node(self.project, question_id)
        if not lookup or not lookup.section:
            return
        self._on_manage_shared_passages_section(lookup.section.section_id)

    def _on_manage_shared_passages_section(self, section_id: str) -> None:
        if not self.project:
            return
        sec = QuestionTreeEngine.find_section(self.project, section_id)
        if not sec:
            return
        from src.ui.workspace.choice_passage_dialog import SharedPassageDialog
        dlg = SharedPassageDialog(sec, parent=self)
        dlg.passage_saved.connect(lambda p: self.tree_structure_changed.emit("Update Shared Passage"))
        dlg.exec()
        self.load_project(self.project)
