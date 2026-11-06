"""Base class for Question Editing Forms (`BaseQuestionForm`)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import QuestionType
from src.core.models.question_model import MarkingScheme, QuestionNode
from src.ui.workspace.rich_text_editor import RichTextEditor


class BaseQuestionForm(QWidget):
    """Base question form providing header metadata, marks, prompt editor, and model solution."""

    form_modified = Signal()
    question_type_changed = Signal(object)  # Emits new QuestionType

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.active_node: Optional[QuestionNode] = None
        self._block_signals = False

        self._build_base_ui()

    def _build_base_ui(self) -> None:
        self.root_lay = QVBoxLayout(self)
        self.root_lay.setContentsMargins(12, 12, 12, 12)
        self.root_lay.setSpacing(10)

        # 1. Top Question Header Strip
        hdr_frame = QFrame()
        hdr_frame.setObjectName("CardFrame")
        hdr_frame.setStyleSheet(
            "#CardFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px; }"
        )
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        hdr_lay.setSpacing(10)

        self.lbl_number = QLabel("Q1.")
        self.lbl_number.setStyleSheet("font-size: 13pt; font-weight: 800; color: #1E293B;")
        hdr_lay.addWidget(self.lbl_number)

        # Question Type Selector
        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.combo_type = QComboBox()
        self.combo_type.setMinimumWidth(150)
        self._populate_type_combo()
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        hdr_lay.addWidget(type_lbl)
        hdr_lay.addWidget(self.combo_type)

        hdr_lay.addSpacing(10)

        # Marks spinbox
        marks_lbl = QLabel("Marks:")
        marks_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_marks = QDoubleSpinBox()
        self.spin_marks.setRange(0.0, 100.0)
        self.spin_marks.setSingleStep(0.5)
        self.spin_marks.setDecimals(1)
        self.spin_marks.setValue(2.0)
        self.spin_marks.setSuffix(" M")
        self.spin_marks.valueChanged.connect(self._on_field_changed)
        hdr_lay.addWidget(marks_lbl)
        hdr_lay.addWidget(self.spin_marks)

        hdr_lay.addSpacing(10)

        # Answer Space Lines (for printed write-in lines)
        lines_lbl = QLabel("Lines:")
        lines_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_lines = QSpinBox()
        self.spin_lines.setRange(0, 100)
        self.spin_lines.setValue(0)
        self.spin_lines.setToolTip("Number of blank response lines printed beneath this question")
        self.spin_lines.valueChanged.connect(self._on_field_changed)
        hdr_lay.addWidget(lines_lbl)
        hdr_lay.addWidget(self.spin_lines)

        # Page Break Before toggle
        self.chk_page_break = QCheckBox("Page Break Before")
        self.chk_page_break.toggled.connect(self._on_field_changed)
        hdr_lay.addWidget(self.chk_page_break)

        hdr_lay.addStretch(1)
        self.root_lay.addWidget(hdr_frame)

        # 2. Main Question Statement / Prompt Editor
        prompt_box = QFrame()
        p_lay = QVBoxLayout(prompt_box)
        p_lay.setContentsMargins(0, 0, 0, 0)
        p_lay.setSpacing(4)

        p_lbl = QLabel("Question Statement / Prompt:")
        p_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        p_lay.addWidget(p_lbl)

        self.editor_prompt = RichTextEditor(placeholder="Enter question text, mathematical formula, or prompt...", parent=self)
        self.editor_prompt.text_changed.connect(self._on_field_changed)
        p_lay.addWidget(self.editor_prompt)
        self.root_lay.addWidget(prompt_box)

        # 3. Container for Specialized Payload Widgets (MCQ options, Match tables, Blanks, etc.)
        self.payload_container = QWidget()
        self.payload_lay = QVBoxLayout(self.payload_container)
        self.payload_lay.setContentsMargins(0, 0, 0, 0)
        self.payload_lay.setSpacing(6)
        self.root_lay.addWidget(self.payload_container)

        # 4. Collapsible Model Solution / Marking Scheme
        self.btn_toggle_solution = QPushButton("▶ Model Answer / Scoring Rubric")
        self.btn_toggle_solution.setCheckable(True)
        self.btn_toggle_solution.setStyleSheet("text-align: left; font-weight: 600; padding: 6px;")
        self.btn_toggle_solution.clicked.connect(self._toggle_solution_drawer)
        self.root_lay.addWidget(self.btn_toggle_solution)

        self.solution_drawer = QWidget()
        s_lay = QVBoxLayout(self.solution_drawer)
        s_lay.setContentsMargins(0, 0, 0, 0)
        s_lay.setSpacing(4)

        self.editor_solution = RichTextEditor(placeholder="Enter model answer or step-by-step scoring rubric...", parent=self)
        self.editor_solution.text_changed.connect(self._on_field_changed)
        s_lay.addWidget(self.editor_solution)

        self.solution_drawer.setVisible(False)
        self.root_lay.addWidget(self.solution_drawer)

    def _populate_type_combo(self) -> None:
        self.combo_type.clear()
        for qt in QuestionType:
            name = qt.value.replace("_", " ").title()
            self.combo_type.addItem(name, qt)

    def _toggle_solution_drawer(self) -> None:
        visible = self.btn_toggle_solution.isChecked()
        self.solution_drawer.setVisible(visible)
        self.btn_toggle_solution.setText("▼ Model Answer / Scoring Rubric" if visible else "▶ Model Answer / Scoring Rubric")

    def load_question(self, node: QuestionNode) -> None:
        """Populate base question fields and dispatch to payload loader."""
        self._block_signals = True
        try:
            self.active_node = node
            label = node.resolved_number or "•"
            self.lbl_number.setText(label)

            idx = self.combo_type.findData(node.question_type)
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)

            self.spin_marks.setValue(node.marks if node.marks is not None else 2.0)
            self.spin_lines.setValue(node.answer_space_lines)
            self.chk_page_break.setChecked(node.page_break_before)

            self.editor_prompt.set_html(node.prompt_html)

            # Load model answer
            if node.marking_scheme and node.marking_scheme.model_answer_html:
                self.editor_solution.set_html(node.marking_scheme.model_answer_html)
                self.btn_toggle_solution.setChecked(True)
                self._toggle_solution_drawer()
            else:
                self.editor_solution.set_html("")

            self._load_payload(node)
        finally:
            self._block_signals = False

    def save_to_question(self, node: QuestionNode) -> None:
        """Write form values back to `node`."""
        node.marks = float(self.spin_marks.value())
        node.answer_space_lines = int(self.spin_lines.value())
        node.page_break_before = self.chk_page_break.isChecked()
        node.prompt_html = self.editor_prompt.get_html()

        sol_html = self.editor_solution.get_html()
        if sol_html and sol_html.strip() and self.editor_solution.get_plain_text().strip():
            if node.marking_scheme is None:
                node.marking_scheme = MarkingScheme()
            node.marking_scheme.model_answer_html = sol_html

        self._save_payload(node)

    def _load_payload(self, node: QuestionNode) -> None:
        """Subclasses override this to load type-specific data."""
        pass

    def _save_payload(self, node: QuestionNode) -> None:
        """Subclasses override this to save type-specific data."""
        pass

    def _on_field_changed(self) -> None:
        if not self._block_signals:
            if self.active_node:
                self.save_to_question(self.active_node)
            self.form_modified.emit()

    def _on_type_changed(self, index: int) -> None:
        if self._block_signals or not self.active_node:
            return
        new_type = self.combo_type.currentData()
        if new_type and new_type != self.active_node.question_type:
            self.question_type_changed.emit(new_type)
