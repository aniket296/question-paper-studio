"""Specialized forms for the 4 Core Question Types (Normal, MCQ, Fill in Blank, Match Pair)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import FillBlankMode, MCQOptionLayout, QuestionType
from src.core.models.question_model import (
    BlankItem,
    FillBlankData,
    MatchPairData,
    MatchPairRow,
    MCQData,
    MCQOption,
    NormalQuestionData,
    QuestionNode,
)
from src.ui.workspace.forms.base_form import BaseQuestionForm


class NormalQuestionForm(BaseQuestionForm):
    """Editor for standard free-form descriptive questions."""

    def _load_payload(self, node: QuestionNode) -> None:
        pass

    def _save_payload(self, node: QuestionNode) -> None:
        if node.type_data is None or not isinstance(node.type_data, NormalQuestionData):
            node.type_data = NormalQuestionData()


# ============================================================================
# MCQ Question Form
# ============================================================================


class MCQOptionRowWidget(QWidget):
    """Visual row for a single MCQ option: [Label] [Correct Check/Radio] [Text Edit] [Delete Button]."""

    option_changed = Signal()
    delete_clicked = Signal(str)  # option_id

    def __init__(
        self,
        option: MCQOption,
        allow_multiple: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.option = option
        self.allow_multiple = allow_multiple

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        self.lbl_label = QLabel(f"({option.label})")
        self.lbl_label.setMinimumWidth(26)
        self.lbl_label.setStyleSheet("font-weight: 700; color: #1E293B;")
        lay.addWidget(self.lbl_label)

        # Correct answer indicator (checkbox if multiple correct allowed, else radio button)
        self.chk_correct = QCheckBox()
        self.chk_correct.setToolTip("Mark as correct answer")
        self.chk_correct.setChecked(option.is_correct)
        self.chk_correct.toggled.connect(self._on_correct_toggled)
        lay.addWidget(self.chk_correct)

        self.edit_text = QLineEdit()
        self.edit_text.setPlaceholderText(f"Option {option.label} text...")
        self.edit_text.setText(option.text_html)
        self.edit_text.textChanged.connect(self._on_text_changed)
        lay.addWidget(self.edit_text, 1)

        self.btn_del = QPushButton("✕")
        self.btn_del.setMaximumWidth(26)
        self.btn_del.setToolTip("Delete this option")
        self.btn_del.clicked.connect(lambda: self.delete_clicked.emit(self.option.id))
        lay.addWidget(self.btn_del)

    def _on_correct_toggled(self, checked: bool) -> None:
        self.option.is_correct = checked
        self.option_changed.emit()

    def _on_text_changed(self, text: str) -> None:
        self.option.text_html = text.strip()
        self.option_changed.emit()

    def update_label(self, label: str) -> None:
        self.lbl_label.setText(f"({label})")
        self.edit_text.setPlaceholderText(f"Option {label} text...")


class MCQQuestionForm(BaseQuestionForm):
    """Editor for Multiple Choice Questions supporting dynamic options, grid layouts, and single/multi correct."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_mcq_ui()

    def _build_mcq_ui(self) -> None:
        mcq_box = QFrame()
        mcq_box.setObjectName("CardFrame")
        mcq_box.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 8px; }"
        )
        box_lay = QVBoxLayout(mcq_box)
        box_lay.setContentsMargins(10, 8, 10, 8)
        box_lay.setSpacing(8)

        # Top MCQ Controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        layout_lbl = QLabel("Option Layout:")
        layout_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.combo_layout = QComboBox()
        self.combo_layout.addItem("Grid (2x2)", MCQOptionLayout.GRID_2X2)
        self.combo_layout.addItem("Inline (Horizontal)", MCQOptionLayout.INLINE)
        self.combo_layout.addItem("Stacked (Vertical)", MCQOptionLayout.STACKED)
        self.combo_layout.currentIndexChanged.connect(self._on_field_changed)
        ctrl_row.addWidget(layout_lbl)
        ctrl_row.addWidget(self.combo_layout)

        ctrl_row.addSpacing(10)

        self.chk_allow_multiple = QCheckBox("Allow Multiple Correct Answers")
        self.chk_allow_multiple.toggled.connect(self._on_allow_multiple_toggled)
        ctrl_row.addWidget(self.chk_allow_multiple)

        ctrl_row.addStretch(1)

        self.btn_add_opt = QPushButton("+ Add Option")
        self.btn_add_opt.setObjectName("PrimaryButton")
        self.btn_add_opt.clicked.connect(self._on_add_option_clicked)
        ctrl_row.addWidget(self.btn_add_opt)

        box_lay.addLayout(ctrl_row)

        # Container for Options list
        self.options_container = QWidget()
        self.options_lay = QVBoxLayout(self.options_container)
        self.options_lay.setContentsMargins(0, 4, 0, 4)
        self.options_lay.setSpacing(4)
        box_lay.addWidget(self.options_container)

        # Validation status message
        self.lbl_validation = QLabel("")
        self.lbl_validation.setStyleSheet("color: #DC2626; font-size: 9.5pt; font-weight: 600;")
        box_lay.addWidget(self.lbl_validation)

        self.payload_lay.addWidget(mcq_box)

    def _load_payload(self, node: QuestionNode) -> None:
        if not isinstance(node.type_data, MCQData):
            node.type_data = MCQData(
                options=[
                    MCQOption(text_html="", is_correct=False, label="A"),
                    MCQOption(text_html="", is_correct=False, label="B"),
                    MCQOption(text_html="", is_correct=False, label="C"),
                    MCQOption(text_html="", is_correct=False, label="D"),
                ]
            )

        data: MCQData = node.type_data
        idx = self.combo_layout.findData(data.option_layout)
        if idx >= 0:
            self.combo_layout.setCurrentIndex(idx)
        self.chk_allow_multiple.setChecked(data.allow_multiple_correct)

        self._rebuild_options_list()

    def _save_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, MCQData):
            data: MCQData = node.type_data
            data.option_layout = self.combo_layout.currentData() or MCQOptionLayout.GRID_2X2
            data.allow_multiple_correct = self.chk_allow_multiple.isChecked()
            data.relabel_options()

    def _rebuild_options_list(self) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MCQData):
            return

        # Clear existing widgets
        while self.options_lay.count():
            item = self.options_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        data: MCQData = self.active_node.type_data
        can_delete = len(data.options) > 2

        for opt in data.options:
            row = MCQOptionRowWidget(opt, allow_multiple=data.allow_multiple_correct, parent=self)
            row.btn_del.setEnabled(can_delete)
            row.option_changed.connect(self._on_option_row_changed)
            row.delete_clicked.connect(self._on_delete_option_clicked)
            self.options_lay.addWidget(row)

        self._validate_mcq_data()

    def _on_option_row_changed(self) -> None:
        # If single correct is enforced and this was checked, uncheck others
        if self.active_node and isinstance(self.active_node.type_data, MCQData):
            data = self.active_node.type_data
            if not data.allow_multiple_correct:
                sender = self.sender()
                if isinstance(sender, MCQOptionRowWidget) and sender.option.is_correct:
                    for i in range(self.options_lay.count()):
                        w = self.options_lay.itemAt(i).widget()
                        if isinstance(w, MCQOptionRowWidget) and w != sender:
                            w.chk_correct.blockSignals(True)
                            w.chk_correct.setChecked(False)
                            w.option.is_correct = False
                            w.chk_correct.blockSignals(False)

        self._validate_mcq_data()
        self._on_field_changed()

    def _on_delete_option_clicked(self, option_id: str) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MCQData):
            return
        data: MCQData = self.active_node.type_data
        if len(data.options) <= 2:
            return

        data.remove_option(option_id)
        self._rebuild_options_list()
        self._on_field_changed()

    def _on_add_option_clicked(self) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MCQData):
            return
        data: MCQData = self.active_node.type_data
        data.add_option(text_html="")
        self._rebuild_options_list()
        self._on_field_changed()

    def _on_allow_multiple_toggled(self, checked: bool) -> None:
        if self.active_node and isinstance(self.active_node.type_data, MCQData):
            self.active_node.type_data.allow_multiple_correct = checked
            # If changing to single correct and multiple are checked, keep only first
            if not checked:
                found_first = False
                for opt in self.active_node.type_data.options:
                    if opt.is_correct:
                        if not found_first:
                            found_first = True
                        else:
                            opt.is_correct = False
            self._rebuild_options_list()
            self._on_field_changed()

    def _validate_mcq_data(self) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MCQData):
            return
        errors = self.active_node.type_data.validate_for_finalization()
        if errors:
            self.lbl_validation.setText("⚠ " + " ".join(errors))
            self.lbl_validation.setVisible(True)
        else:
            self.lbl_validation.setVisible(False)


# ============================================================================
# Fill in the Blank Question Form
# ============================================================================


class FillBlankQuestionForm(BaseQuestionForm):
    """Editor for Fill in the Blank questions with optional word bank and blank insertion helper."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_fill_blank_ui()

    def _build_fill_blank_ui(self) -> None:
        fb_box = QFrame()
        fb_box.setObjectName("CardFrame")
        fb_box.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 8px; }"
        )
        box_lay = QVBoxLayout(fb_box)
        box_lay.setContentsMargins(10, 8, 10, 8)
        box_lay.setSpacing(8)

        top_row = QHBoxLayout()
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Without Options (Standard Fill in Blank)", FillBlankMode.WITHOUT_OPTIONS)
        self.combo_mode.addItem("With Word Bank / Options Box", FillBlankMode.WITH_OPTIONS)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        top_row.addWidget(mode_lbl)
        top_row.addWidget(self.combo_mode)

        top_row.addSpacing(10)

        self.btn_insert_blank = QPushButton("+ Insert Blank (______)")
        self.btn_insert_blank.setToolTip("Insert a 6-character blank line into the prompt statement at cursor")
        self.btn_insert_blank.clicked.connect(self._on_insert_blank_clicked)
        top_row.addWidget(self.btn_insert_blank)

        top_row.addStretch(1)
        box_lay.addLayout(top_row)

        # Word bank options row (shown only if with_options)
        self.word_bank_widget = QWidget()
        wb_lay = QHBoxLayout(self.word_bank_widget)
        wb_lay.setContentsMargins(0, 0, 0, 0)
        wb_lbl = QLabel("Word Bank Items:")
        wb_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_word_bank = QLineEdit()
        self.edit_word_bank.setPlaceholderText("Comma-separated options (e.g. kinetic, potential, friction)")
        self.edit_word_bank.textChanged.connect(self._on_field_changed)
        wb_lay.addWidget(wb_lbl)
        wb_lay.addWidget(self.edit_word_bank, 1)
        self.word_bank_widget.setVisible(False)
        box_lay.addWidget(self.word_bank_widget)

        # Blanks ground truth answer row
        ans_row = QHBoxLayout()
        ans_lbl = QLabel("Expected Blank Answers:")
        ans_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_blank_answers = QLineEdit()
        self.edit_blank_answers.setPlaceholderText("Comma-separated correct answers for Blank 1, Blank 2...")
        self.edit_blank_answers.textChanged.connect(self._on_field_changed)
        ans_row.addWidget(ans_lbl)
        ans_row.addWidget(self.edit_blank_answers, 1)
        box_lay.addLayout(ans_row)

        self.payload_lay.addWidget(fb_box)

    def _on_insert_blank_clicked(self) -> None:
        self.editor_prompt.txt_edit.insertPlainText("______")
        self.editor_prompt.txt_edit.setFocus()

    def _on_mode_changed(self) -> None:
        is_wb = self.combo_mode.currentData() == FillBlankMode.WITH_OPTIONS
        self.word_bank_widget.setVisible(is_wb)
        self._on_field_changed()

    def _load_payload(self, node: QuestionNode) -> None:
        if not isinstance(node.type_data, FillBlankData):
            node.type_data = FillBlankData()

        data: FillBlankData = node.type_data
        idx = self.combo_mode.findData(data.mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)
        self.word_bank_widget.setVisible(data.mode == FillBlankMode.WITH_OPTIONS)

        self.edit_word_bank.setText(", ".join(data.word_bank_options))
        answers = [b.correct_answer for b in data.blanks]
        self.edit_blank_answers.setText(", ".join(answers))

    def _save_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, FillBlankData):
            data: FillBlankData = node.type_data
            data.mode = self.combo_mode.currentData() or FillBlankMode.WITHOUT_OPTIONS
            raw_wb = self.edit_word_bank.text()
            data.word_bank_options = [w.strip() for w in raw_wb.split(",") if w.strip()]

            raw_ans = self.edit_blank_answers.text()
            answers = [a.strip() for a in raw_ans.split(",") if a.strip()]
            data.blanks = [
                BlankItem(blank_index=i + 1, correct_answer=ans)
                for i, ans in enumerate(answers)
            ] or [BlankItem(blank_index=1, correct_answer="")]


# ============================================================================
# Match the Pair Question Form
# ============================================================================


class MatchPairQuestionForm(BaseQuestionForm):
    """Editor for Match the Pair questions with dual-column tabular rows and correct match mapping."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_match_ui()

    def _build_match_ui(self) -> None:
        mp_box = QFrame()
        mp_box.setObjectName("CardFrame")
        mp_box.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 8px; }"
        )
        box_lay = QVBoxLayout(mp_box)
        box_lay.setContentsMargins(10, 8, 10, 8)
        box_lay.setSpacing(8)

        # Header Titles Row
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(10)

        a_lbl = QLabel("Column A Header:")
        a_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_col_a = QLineEdit("Column A")
        self.edit_col_a.textChanged.connect(self._on_field_changed)
        hdr_row.addWidget(a_lbl)
        hdr_row.addWidget(self.edit_col_a, 1)

        b_lbl = QLabel("Column B Header:")
        b_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_col_b = QLineEdit("Column B")
        self.edit_col_b.textChanged.connect(self._on_field_changed)
        hdr_row.addWidget(b_lbl)
        hdr_row.addWidget(self.edit_col_b, 1)

        self.btn_add_pair = QPushButton("+ Add Pair")
        self.btn_add_pair.setObjectName("PrimaryButton")
        self.btn_add_pair.clicked.connect(self._on_add_pair_clicked)
        hdr_row.addWidget(self.btn_add_pair)

        box_lay.addLayout(hdr_row)

        # Pairs Table Widget
        self.table_pairs = QTableWidget(0, 3)
        self.table_pairs.setHorizontalHeaderLabels(["Left Item (Col A)", "Matching Target (Col B)", "Action"])
        self.table_pairs.horizontalHeader().setStretchLastSection(False)
        self.table_pairs.setColumnWidth(2, 60)
        self.table_pairs.horizontalHeader().setSectionResizeMode(0, self.table_pairs.horizontalHeader().ResizeMode.Stretch)
        self.table_pairs.horizontalHeader().setSectionResizeMode(1, self.table_pairs.horizontalHeader().ResizeMode.Stretch)
        self.table_pairs.setAlternatingRowColors(True)
        self.table_pairs.setMaximumHeight(220)
        self.table_pairs.cellChanged.connect(self._on_cell_changed)
        box_lay.addWidget(self.table_pairs)

        # Options footer
        ftr_row = QHBoxLayout()
        self.chk_shuffle = QCheckBox("Shuffle Column B in Student Question Paper")
        self.chk_shuffle.toggled.connect(self._on_field_changed)
        ftr_row.addWidget(self.chk_shuffle)
        ftr_row.addStretch(1)
        box_lay.addLayout(ftr_row)

        self.payload_lay.addWidget(mp_box)

    def _load_payload(self, node: QuestionNode) -> None:
        if not isinstance(node.type_data, MatchPairData):
            node.type_data = MatchPairData(
                rows=[
                    MatchPairRow(col_a_html="Item 1", col_b_html="Match 1"),
                    MatchPairRow(col_a_html="Item 2", col_b_html="Match 2"),
                ]
            )

        data: MatchPairData = node.type_data
        self.edit_col_a.setText(data.col_a_header)
        self.edit_col_b.setText(data.col_b_header)
        self.chk_shuffle.setChecked(data.shuffle_col_b)

        self._populate_table()

    def _populate_table(self) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MatchPairData):
            return

        data: MatchPairData = self.active_node.type_data
        self.table_pairs.blockSignals(True)
        self.table_pairs.setRowCount(len(data.rows))

        can_delete = len(data.rows) > 2
        for r, row in enumerate(data.rows):
            item_a = QTableWidgetItem(row.col_a_html)
            item_b = QTableWidgetItem(row.col_b_html)
            self.table_pairs.setItem(r, 0, item_a)
            self.table_pairs.setItem(r, 1, item_b)

            btn_del = QPushButton("✕")
            btn_del.setMaximumWidth(28)
            btn_del.setEnabled(can_delete)
            btn_del.clicked.connect(lambda _, rid=row.id: self._on_delete_row(rid))
            self.table_pairs.setCellWidget(r, 2, btn_del)

        self.table_pairs.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MatchPairData):
            return
        data: MatchPairData = self.active_node.type_data
        if row < len(data.rows):
            item = self.table_pairs.item(row, col)
            text = item.text().strip() if item else ""
            if col == 0:
                data.rows[row].col_a_html = text
            elif col == 1:
                data.rows[row].col_b_html = text
            self._on_field_changed()

    def _on_add_pair_clicked(self) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MatchPairData):
            return
        data: MatchPairData = self.active_node.type_data
        data.add_row(col_a_html="", col_b_html="")
        self._populate_table()
        self._on_field_changed()

    def _on_delete_row(self, row_id: str) -> None:
        if not self.active_node or not isinstance(self.active_node.type_data, MatchPairData):
            return
        data: MatchPairData = self.active_node.type_data
        if len(data.rows) <= 2:
            return
        data.rows = [r for r in data.rows if r.id != row_id]
        self._populate_table()
        self._on_field_changed()

    def _save_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, MatchPairData):
            data: MatchPairData = node.type_data
            data.col_a_header = self.edit_col_a.text().strip() or "Column A"
            data.col_b_header = self.edit_col_b.text().strip() or "Column B"
            data.shuffle_col_b = self.chk_shuffle.isChecked()


def create_question_form(node: QuestionNode, parent: Optional[QWidget] = None) -> BaseQuestionForm:
    """Factory creating the specialized editor form for `node.question_type`."""
    if node.question_type == QuestionType.MCQ:
        form = MCQQuestionForm(parent)
    elif node.question_type == QuestionType.FILL_IN_THE_BLANK:
        form = FillBlankQuestionForm(parent)
    elif node.question_type == QuestionType.MATCH_THE_PAIR:
        form = MatchPairQuestionForm(parent)
    else:
        # Default fallback to Normal descriptive question form
        form = NormalQuestionForm(parent)

    form.load_question(node)
    return form
