"""Specialized forms for the 9 Optional Progressive Disclosure Question Types.

Includes:
1. TrueFalseQuestionForm
2. ShortAnswerQuestionForm
3. LongAnswerQuestionForm
4. AssertionReasonQuestionForm
5. CaseBasedQuestionForm
6. NumericalDynamicQuestionForm
7. OrderingSequencingQuestionForm
8. DiagramLabellingQuestionForm
9. SourceBasedQuestionForm
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.models.enums import QuestionType
from src.core.models.question_model import (
    AssertionReasonData,
    CaseBasedData,
    DiagramLabelHotspot,
    DiagramLabellingData,
    LongAnswerData,
    NumericalDynamicData,
    NumericVariableRange,
    OrderingItem,
    OrderingSequencingData,
    QuestionNode,
    ShortAnswerData,
    SourceBasedData,
    TrueFalseData,
)
from src.ui.workspace.forms.base_form import BaseQuestionForm
from src.ui.workspace.rich_text_editor import RichTextEditor


# ============================================================================
# 1. True / False Question Form
# ============================================================================

class TrueFalseQuestionForm(BaseQuestionForm):
    """Editor for True / False questions with optional justification requirement."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("True / False Parameters")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Radio button choice for correct answer
        choice_box = QHBoxLayout()
        choice_lbl = QLabel("Correct Answer:")
        choice_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        choice_box.addWidget(choice_lbl)

        self.btn_group = QButtonGroup(self)
        self.rb_true = QRadioButton("True")
        self.rb_false = QRadioButton("False")
        self.rb_true.setChecked(True)
        self.btn_group.addButton(self.rb_true, 1)
        self.btn_group.addButton(self.rb_false, 0)
        self.rb_true.toggled.connect(self._on_field_changed)
        self.rb_false.toggled.connect(self._on_field_changed)
        choice_box.addWidget(self.rb_true)
        choice_box.addWidget(self.rb_false)
        choice_box.addStretch(1)
        g_lay.addLayout(choice_box)

        # Justification requirement
        self.chk_justification = QCheckBox("Require candidate to provide reasoning / justification")
        self.chk_justification.toggled.connect(self._on_field_changed)
        g_lay.addWidget(self.chk_justification)

        self.payload_lay.addWidget(group)

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, TrueFalseData):
            data: TrueFalseData = node.type_data
            if data.correct_is_true is True:
                self.rb_true.setChecked(True)
            elif data.correct_is_true is False:
                self.rb_false.setChecked(True)
            self.chk_justification.setChecked(data.require_justification)

    def _save_payload(self, node: QuestionNode) -> None:
        node.type_data = TrueFalseData(
            correct_is_true=self.rb_true.isChecked(),
            require_justification=self.chk_justification.isChecked(),
        )


# ============================================================================
# 2. Short Answer Question Form
# ============================================================================

class ShortAnswerQuestionForm(BaseQuestionForm):
    """Editor for Short Answer questions with word limit and expected keywords."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Short Answer Configuration")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Word limit row
        w_row = QHBoxLayout()
        w_lbl = QLabel("Suggested Word Limit:")
        w_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_word_limit = QSpinBox()
        self.spin_word_limit.setRange(10, 500)
        self.spin_word_limit.setValue(50)
        self.spin_word_limit.setSuffix(" words")
        self.spin_word_limit.valueChanged.connect(self._on_field_changed)
        w_row.addWidget(w_lbl)
        w_row.addWidget(self.spin_word_limit)
        w_row.addStretch(1)
        g_lay.addLayout(w_row)

        # Expected keywords / key concepts row
        kw_lbl = QLabel("Expected Keywords / Key Concepts for Evaluation:")
        kw_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        g_lay.addWidget(kw_lbl)

        add_row = QHBoxLayout()
        self.txt_keyword = QLineEdit()
        self.txt_keyword.setPlaceholderText("Enter a keyword or key phrase and press Add...")
        self.txt_keyword.returnPressed.connect(self._on_add_keyword)
        self.btn_add_kw = QPushButton("+ Add Keyword")
        self.btn_add_kw.clicked.connect(self._on_add_keyword)
        add_row.addWidget(self.txt_keyword, 1)
        add_row.addWidget(self.btn_add_kw)
        g_lay.addLayout(add_row)

        self.table_keywords = QTableWidget(0, 2)
        self.table_keywords.setHorizontalHeaderLabels(["Expected Keyword / Concept", "Action"])
        self.table_keywords.horizontalHeader().setStretchLastSection(False)
        self.table_keywords.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_keywords.setMaximumHeight(140)
        g_lay.addWidget(self.table_keywords)

        self.payload_lay.addWidget(group)

    def _on_add_keyword(self) -> None:
        text = self.txt_keyword.text().strip()
        if not text:
            return
        self.txt_keyword.clear()
        row = self.table_keywords.rowCount()
        self.table_keywords.insertRow(row)
        self.table_keywords.setItem(row, 0, QTableWidgetItem(text))

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda: self._on_delete_keyword(row))
        self.table_keywords.setCellWidget(row, 1, btn_del)
        self._on_field_changed()

    def _on_delete_keyword(self, row_idx: int) -> None:
        self.table_keywords.removeRow(row_idx)
        # Refresh delete button callbacks
        for r in range(self.table_keywords.rowCount()):
            btn = QPushButton("Delete")
            btn.setStyleSheet("color: #DC2626;")
            btn.clicked.connect(lambda checked=False, curr=r: self._on_delete_keyword(curr))
            self.table_keywords.setCellWidget(r, 1, btn)
        self._on_field_changed()

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, ShortAnswerData):
            data: ShortAnswerData = node.type_data
            self.spin_word_limit.setValue(data.word_limit or 50)
            self.table_keywords.setRowCount(0)
            for kw in data.expected_keywords:
                row = self.table_keywords.rowCount()
                self.table_keywords.insertRow(row)
                self.table_keywords.setItem(row, 0, QTableWidgetItem(kw))
                btn_del = QPushButton("Delete")
                btn_del.setStyleSheet("color: #DC2626;")
                btn_del.clicked.connect(lambda checked=False, r=row: self._on_delete_keyword(r))
                self.table_keywords.setCellWidget(row, 1, btn_del)

    def _save_payload(self, node: QuestionNode) -> None:
        kws = [
            self.table_keywords.item(r, 0).text().strip()
            for r in range(self.table_keywords.rowCount())
            if self.table_keywords.item(r, 0) and self.table_keywords.item(r, 0).text().strip()
        ]
        node.type_data = ShortAnswerData(
            word_limit=self.spin_word_limit.value(),
            expected_keywords=kws,
        )


# ============================================================================
# 3. Long Answer / Essay Question Form
# ============================================================================

class LongAnswerQuestionForm(BaseQuestionForm):
    """Editor for Long / Essay Answer questions with evaluation rubric criteria."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Long / Essay Answer Configuration")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Word limit row
        w_row = QHBoxLayout()
        w_lbl = QLabel("Suggested Word Limit:")
        w_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_word_limit = QSpinBox()
        self.spin_word_limit.setRange(50, 2000)
        self.spin_word_limit.setValue(250)
        self.spin_word_limit.setSuffix(" words")
        self.spin_word_limit.valueChanged.connect(self._on_field_changed)
        w_row.addWidget(w_lbl)
        w_row.addWidget(self.spin_word_limit)
        w_row.addStretch(1)
        g_lay.addLayout(w_row)

        # Evaluation criteria table
        crit_lbl = QLabel("Scoring Rubric & Evaluation Criteria:")
        crit_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        g_lay.addWidget(crit_lbl)

        add_row = QHBoxLayout()
        self.txt_criterion = QLineEdit()
        self.txt_criterion.setPlaceholderText("e.g. Introduction & Definition (1 M), Analysis & Examples (3 M)...")
        self.txt_criterion.returnPressed.connect(self._on_add_criterion)
        self.btn_add_crit = QPushButton("+ Add Criterion")
        self.btn_add_crit.clicked.connect(self._on_add_criterion)
        add_row.addWidget(self.txt_criterion, 1)
        add_row.addWidget(self.btn_add_crit)
        g_lay.addLayout(add_row)

        self.table_criteria = QTableWidget(0, 2)
        self.table_criteria.setHorizontalHeaderLabels(["Criterion / Step Breakdown", "Action"])
        self.table_criteria.horizontalHeader().setStretchLastSection(False)
        self.table_criteria.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_criteria.setMaximumHeight(150)
        g_lay.addWidget(self.table_criteria)

        self.payload_lay.addWidget(group)

    def _on_add_criterion(self) -> None:
        text = self.txt_criterion.text().strip()
        if not text:
            return
        self.txt_criterion.clear()
        row = self.table_criteria.rowCount()
        self.table_criteria.insertRow(row)
        self.table_criteria.setItem(row, 0, QTableWidgetItem(text))

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda: self._on_delete_criterion(row))
        self.table_criteria.setCellWidget(row, 1, btn_del)
        self._on_field_changed()

    def _on_delete_criterion(self, row_idx: int) -> None:
        self.table_criteria.removeRow(row_idx)
        for r in range(self.table_criteria.rowCount()):
            btn = QPushButton("Delete")
            btn.setStyleSheet("color: #DC2626;")
            btn.clicked.connect(lambda checked=False, curr=r: self._on_delete_criterion(curr))
            self.table_criteria.setCellWidget(r, 1, btn)
        self._on_field_changed()

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, LongAnswerData):
            data: LongAnswerData = node.type_data
            self.spin_word_limit.setValue(data.word_limit or 250)
            self.table_criteria.setRowCount(0)
            for c in data.evaluation_criteria:
                row = self.table_criteria.rowCount()
                self.table_criteria.insertRow(row)
                self.table_criteria.setItem(row, 0, QTableWidgetItem(c))
                btn_del = QPushButton("Delete")
                btn_del.setStyleSheet("color: #DC2626;")
                btn_del.clicked.connect(lambda checked=False, r=row: self._on_delete_criterion(r))
                self.table_criteria.setCellWidget(row, 1, btn_del)

    def _save_payload(self, node: QuestionNode) -> None:
        crit = [
            self.table_criteria.item(r, 0).text().strip()
            for r in range(self.table_criteria.rowCount())
            if self.table_criteria.item(r, 0) and self.table_criteria.item(r, 0).text().strip()
        ]
        node.type_data = LongAnswerData(
            word_limit=self.spin_word_limit.value(),
            evaluation_criteria=crit,
        )


# ============================================================================
# 4. Assertion & Reason Question Form
# ============================================================================

class AssertionReasonQuestionForm(BaseQuestionForm):
    """Editor for Assertion & Reason questions with CBSE standard 4-choice preset."""

    STANDARD_OPTIONS = [
        "Both Assertion (A) and Reason (R) are true and R is the correct explanation of A.",
        "Both Assertion (A) and Reason (R) are true, but R is not the correct explanation of A.",
        "Assertion (A) is true, but Reason (R) is false.",
        "Assertion (A) is false, but Reason (R) is true.",
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Assertion (A) & Reason (R) Statements")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Assertion Editor
        a_lbl = QLabel("Assertion (A) Statement:")
        a_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        g_lay.addWidget(a_lbl)
        self.editor_assertion = RichTextEditor(placeholder="Enter Assertion (A) statement with equations or formulas...", parent=self)
        self.editor_assertion.text_changed.connect(self._on_field_changed)
        g_lay.addWidget(self.editor_assertion)

        # Reason Editor
        r_lbl = QLabel("Reason (R) Statement:")
        r_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        g_lay.addWidget(r_lbl)
        self.editor_reason = RichTextEditor(placeholder="Enter Reason (R) statement with equations or formulas...", parent=self)
        self.editor_reason.text_changed.connect(self._on_field_changed)
        g_lay.addWidget(self.editor_reason)

        # Correct option preset selector
        opt_group = QGroupBox("Standard Evaluation Key")
        opt_lay = QVBoxLayout(opt_group)
        self.combo_correct = QComboBox()
        self.combo_correct.addItem("(A) Both A and R are true, and R is correct explanation of A", 0)
        self.combo_correct.addItem("(B) Both A and R are true, but R is NOT correct explanation of A", 1)
        self.combo_correct.addItem("(C) Assertion (A) is true, but Reason (R) is false", 2)
        self.combo_correct.addItem("(D) Assertion (A) is false, but Reason (R) is true", 3)
        self.combo_correct.currentIndexChanged.connect(self._on_field_changed)
        opt_lay.addWidget(self.combo_correct)
        g_lay.addWidget(opt_group)

        self.payload_lay.addWidget(group)

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, AssertionReasonData):
            data: AssertionReasonData = node.type_data
            self.editor_assertion.set_html(data.assertion_html)
            self.editor_reason.set_html(data.reason_html)
            idx = max(0, min(3, data.correct_option_index))
            self.combo_correct.setCurrentIndex(idx)

    def _save_payload(self, node: QuestionNode) -> None:
        node.type_data = AssertionReasonData(
            assertion_html=self.editor_assertion.get_html(),
            reason_html=self.editor_reason.get_html(),
            options=list(self.STANDARD_OPTIONS),
            correct_option_index=self.combo_correct.currentIndex(),
        )


# ============================================================================
# 5. Case-Based / Comprehension Question Form
# ============================================================================

class CaseBasedQuestionForm(BaseQuestionForm):
    """Editor for Case-Based / Passage Comprehension stimulus."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Case Study / Reading Stimulus")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Case title
        t_row = QHBoxLayout()
        t_lbl = QLabel("Case Title:")
        t_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("e.g. Case Study: Hydraulic Braking System in Modern Automobiles")
        self.txt_title.textChanged.connect(self._on_field_changed)
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.txt_title, 1)
        g_lay.addLayout(t_row)

        # Case passage editor
        p_lbl = QLabel("Case Passage / Stimulus Text:")
        p_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        g_lay.addWidget(p_lbl)
        self.editor_passage = RichTextEditor(placeholder="Enter comprehension passage, data table, or case context...", parent=self)
        self.editor_passage.text_changed.connect(self._on_field_changed)
        g_lay.addWidget(self.editor_passage)

        # Helper note
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 4px; padding: 6px;")
        i_lay = QHBoxLayout(info_frame)
        i_lbl = QLabel("💡 Tip: Sub-questions based on this case study can be added as child nodes in the Outline Tree on the left.")
        i_lbl.setStyleSheet("color: #1E40AF; font-size: 9pt;")
        i_lay.addWidget(i_lbl)
        g_lay.addWidget(info_frame)

        self.payload_lay.addWidget(group)

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, CaseBasedData):
            data: CaseBasedData = node.type_data
            self.txt_title.setText(data.case_title)
            self.editor_passage.set_html(data.case_passage_html)

    def _save_payload(self, node: QuestionNode) -> None:
        node.type_data = CaseBasedData(
            case_title=self.txt_title.text().strip(),
            case_passage_html=self.editor_passage.get_html(),
        )


# ============================================================================
# 6. Parameterized Numerical Dynamic Question Form
# ============================================================================

class NumericalDynamicQuestionForm(BaseQuestionForm):
    """Editor for Dynamic Numerical questions with formula parsing and variable ranges."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Dynamic Formula & Parameterized Variables")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Formula expression row
        f_row = QHBoxLayout()
        f_lbl = QLabel("Formula Expression:")
        f_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        self.txt_formula = QLineEdit()
        self.txt_formula.setPlaceholderText("e.g. m * g * h  or  v**2 / (2 * a)  or  P * (1 + r/100)**t")
        self.txt_formula.textChanged.connect(self._on_field_changed)
        f_row.addWidget(f_lbl)
        f_row.addWidget(self.txt_formula, 1)
        g_lay.addLayout(f_row)

        # Unit and tolerance row
        u_row = QHBoxLayout()
        u_lbl = QLabel("Unit:")
        u_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_unit = QLineEdit()
        self.txt_unit.setPlaceholderText("e.g. J, m/s^2, kg, Pa")
        self.txt_unit.setMaximumWidth(120)
        self.txt_unit.textChanged.connect(self._on_field_changed)

        tol_lbl = QLabel("Tolerance:")
        tol_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_tolerance = QDoubleSpinBox()
        self.spin_tolerance.setRange(0.0, 100.0)
        self.spin_tolerance.setSingleStep(0.01)
        self.spin_tolerance.setDecimals(3)
        self.spin_tolerance.setValue(0.01)
        self.spin_tolerance.valueChanged.connect(self._on_field_changed)

        u_row.addWidget(u_lbl)
        u_row.addWidget(self.txt_unit)
        u_row.addSpacing(16)
        u_row.addWidget(tol_lbl)
        u_row.addWidget(self.spin_tolerance)
        u_row.addStretch(1)
        g_lay.addLayout(u_row)

        # Parameterized variables table
        v_lbl = QLabel("Variable Ranges (Use {{var_name}} in prompt statement above):")
        v_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        g_lay.addWidget(v_lbl)

        btn_row = QHBoxLayout()
        self.btn_add_var = QPushButton("+ Add Variable")
        self.btn_add_var.clicked.connect(self._on_add_variable)
        self.btn_test_calc = QPushButton("⚡ Test Formula Solver")
        self.btn_test_calc.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: 600;")
        self.btn_test_calc.clicked.connect(self._on_test_formula)
        btn_row.addWidget(self.btn_add_var)
        btn_row.addWidget(self.btn_test_calc)
        btn_row.addStretch(1)
        g_lay.addLayout(btn_row)

        self.table_vars = QTableWidget(0, 6)
        self.table_vars.setHorizontalHeaderLabels(["Variable", "Min", "Max", "Decimals", "Step", "Action"])
        self.table_vars.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_vars.setMaximumHeight(160)
        self.table_vars.cellChanged.connect(lambda r, c: self._on_field_changed())
        g_lay.addWidget(self.table_vars)

        # Test solver feedback label
        self.lbl_calc_feedback = QLabel("Test formula solver to preview instantiated sample values.")
        self.lbl_calc_feedback.setStyleSheet("color: #64748B; font-style: italic;")
        g_lay.addWidget(self.lbl_calc_feedback)

        self.payload_lay.addWidget(group)

    def _on_add_variable(self) -> None:
        row = self.table_vars.rowCount()
        self.table_vars.insertRow(row)
        var_name = f"var_{row + 1}"
        self.table_vars.setItem(row, 0, QTableWidgetItem(var_name))
        self.table_vars.setItem(row, 1, QTableWidgetItem("1.0"))
        self.table_vars.setItem(row, 2, QTableWidgetItem("10.0"))
        self.table_vars.setItem(row, 3, QTableWidgetItem("0"))
        self.table_vars.setItem(row, 4, QTableWidgetItem("1.0"))

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda: self._on_delete_variable(row))
        self.table_vars.setCellWidget(row, 5, btn_del)
        self._on_field_changed()

    def _on_delete_variable(self, row_idx: int) -> None:
        self.table_vars.removeRow(row_idx)
        for r in range(self.table_vars.rowCount()):
            btn = QPushButton("Delete")
            btn.setStyleSheet("color: #DC2626;")
            btn.clicked.connect(lambda checked=False, curr=r: self._on_delete_variable(curr))
            self.table_vars.setCellWidget(r, 5, btn)
        self._on_field_changed()

    def _on_test_formula(self) -> None:
        formula = self.txt_formula.text().strip()
        if not formula:
            self.lbl_calc_feedback.setText("⚠ Please enter a formula expression first.")
            return

        # Extract sampled bindings
        bindings: Dict[str, float] = {}
        for r in range(self.table_vars.rowCount()):
            name_item = self.table_vars.item(r, 0)
            min_item = self.table_vars.item(r, 1)
            max_item = self.table_vars.item(r, 2)
            if name_item and min_item and max_item:
                name = name_item.text().strip()
                try:
                    val = (float(min_item.text()) + float(max_item.text())) / 2.0
                    bindings[name] = val
                except ValueError:
                    pass

        try:
            res = DynamicNumericEngine.evaluate_formula(formula, bindings)
            u_str = f" {self.txt_unit.text().strip()}" if self.txt_unit.text().strip() else ""
            b_str = ", ".join(f"{k}={v:g}" for k, v in bindings.items())
            self.lbl_calc_feedback.setText(f"✓ Valid Formula! Result = {res:g}{u_str} (for {b_str})")
            self.lbl_calc_feedback.setStyleSheet("color: #059669; font-weight: 600;")
        except Exception as e:
            self.lbl_calc_feedback.setText(f"✗ Calculation Error: {e}")
            self.lbl_calc_feedback.setStyleSheet("color: #DC2626; font-weight: 600;")

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, NumericalDynamicData):
            data: NumericalDynamicData = node.type_data
            self.txt_formula.setText(data.formula_expr)
            self.txt_unit.setText(data.unit)
            self.spin_tolerance.setValue(data.answer_tolerance)

            self.table_vars.setRowCount(0)
            for name, v_range in data.variables.items():
                r = self.table_vars.rowCount()
                self.table_vars.insertRow(r)
                self.table_vars.setItem(r, 0, QTableWidgetItem(name))
                self.table_vars.setItem(r, 1, QTableWidgetItem(str(v_range.min_val)))
                self.table_vars.setItem(r, 2, QTableWidgetItem(str(v_range.max_val)))
                self.table_vars.setItem(r, 3, QTableWidgetItem(str(v_range.precision)))
                self.table_vars.setItem(r, 4, QTableWidgetItem(str(v_range.step or "")))

                btn_del = QPushButton("Delete")
                btn_del.setStyleSheet("color: #DC2626;")
                btn_del.clicked.connect(lambda checked=False, curr=r: self._on_delete_variable(curr))
                self.table_vars.setCellWidget(r, 5, btn_del)

    def _save_payload(self, node: QuestionNode) -> None:
        vars_dict: Dict[str, NumericVariableRange] = {}
        for r in range(self.table_vars.rowCount()):
            name_item = self.table_vars.item(r, 0)
            if not name_item or not name_item.text().strip():
                continue
            name = name_item.text().strip()
            min_v = float(self.table_vars.item(r, 1).text()) if self.table_vars.item(r, 1) else 1.0
            max_v = float(self.table_vars.item(r, 2).text()) if self.table_vars.item(r, 2) else 10.0
            prec = int(self.table_vars.item(r, 3).text()) if self.table_vars.item(r, 3) else 0
            step_t = self.table_vars.item(r, 4).text().strip() if self.table_vars.item(r, 4) else ""
            step_v = float(step_t) if step_t else None

            vars_dict[name] = NumericVariableRange(
                min_val=min_v,
                max_val=max_v,
                precision=prec,
                step=step_v,
            )

        node.type_data = NumericalDynamicData(
            formula_expr=self.txt_formula.text().strip(),
            unit=self.txt_unit.text().strip(),
            answer_tolerance=self.spin_tolerance.value(),
            variables=vars_dict,
        )


# ============================================================================
# 7. Ordering / Sequencing Question Form
# ============================================================================

class OrderingSequencingQuestionForm(BaseQuestionForm):
    """Editor for Ordering / Chronological Sequencing questions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Chronological / Process Sequence Steps")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        inst_lbl = QLabel("Enter items in their CORRECT 1-based order. They will be shuffled on the candidate paper.")
        inst_lbl.setStyleSheet("color: #64748B; font-size: 9pt;")
        g_lay.addWidget(inst_lbl)

        btn_row = QHBoxLayout()
        self.btn_add_item = QPushButton("+ Add Step")
        self.btn_add_item.clicked.connect(self._on_add_item)
        self.btn_move_up = QPushButton("↑ Move Up")
        self.btn_move_up.clicked.connect(self._on_move_up)
        self.btn_move_down = QPushButton("↓ Move Down")
        self.btn_move_down.clicked.connect(self._on_move_down)
        btn_row.addWidget(self.btn_add_item)
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        btn_row.addStretch(1)
        g_lay.addLayout(btn_row)

        self.table_items = QTableWidget(0, 3)
        self.table_items.setHorizontalHeaderLabels(["Order", "Step Statement / Item", "Action"])
        self.table_items.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_items.setMaximumHeight(180)
        self.table_items.cellChanged.connect(lambda r, c: self._on_field_changed())
        g_lay.addWidget(self.table_items)

        self.payload_lay.addWidget(group)

    def _on_add_item(self) -> None:
        row = self.table_items.rowCount()
        self.table_items.insertRow(row)
        self.table_items.setItem(row, 0, QTableWidgetItem(f"Step {row + 1}"))
        self.table_items.setItem(row, 1, QTableWidgetItem(f"Event / Process step {row + 1}"))

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda: self._on_delete_item(row))
        self.table_items.setCellWidget(row, 2, btn_del)
        self._on_field_changed()

    def _on_delete_item(self, row_idx: int) -> None:
        self.table_items.removeRow(row_idx)
        self._reindex_items()
        self._on_field_changed()

    def _on_move_up(self) -> None:
        curr = self.table_items.currentRow()
        if curr > 0:
            self._swap_rows(curr, curr - 1)
            self.table_items.setCurrentCell(curr - 1, 1)

    def _on_move_down(self) -> None:
        curr = self.table_items.currentRow()
        if curr >= 0 and curr < self.table_items.rowCount() - 1:
            self._swap_rows(curr, curr + 1)
            self.table_items.setCurrentCell(curr + 1, 1)

    def _swap_rows(self, r1: int, r2: int) -> None:
        t1 = self.table_items.item(r1, 1).text() if self.table_items.item(r1, 1) else ""
        t2 = self.table_items.item(r2, 1).text() if self.table_items.item(r2, 1) else ""
        self.table_items.item(r1, 1).setText(t2)
        self.table_items.item(r2, 1).setText(t1)
        self._reindex_items()
        self._on_field_changed()

    def _reindex_items(self) -> None:
        for r in range(self.table_items.rowCount()):
            if self.table_items.item(r, 0):
                self.table_items.item(r, 0).setText(f"Step {r + 1}")
            btn = QPushButton("Delete")
            btn.setStyleSheet("color: #DC2626;")
            btn.clicked.connect(lambda checked=False, curr=r: self._on_delete_item(curr))
            self.table_items.setCellWidget(r, 2, btn)

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, OrderingSequencingData):
            data: OrderingSequencingData = node.type_data
            self.table_items.setRowCount(0)
            sorted_items = sorted(data.items, key=lambda x: x.correct_position)
            for idx, item in enumerate(sorted_items):
                r = self.table_items.rowCount()
                self.table_items.insertRow(r)
                self.table_items.setItem(r, 0, QTableWidgetItem(f"Step {idx + 1}"))
                self.table_items.setItem(r, 1, QTableWidgetItem(item.text_html))
                btn_del = QPushButton("Delete")
                btn_del.setStyleSheet("color: #DC2626;")
                btn_del.clicked.connect(lambda checked=False, curr=r: self._on_delete_item(curr))
                self.table_items.setCellWidget(r, 2, btn_del)

    def _save_payload(self, node: QuestionNode) -> None:
        items = []
        for r in range(self.table_items.rowCount()):
            text = self.table_items.item(r, 1).text().strip() if self.table_items.item(r, 1) else ""
            items.append(OrderingItem(text_html=text, correct_position=r + 1))
        node.type_data = OrderingSequencingData(items=items)


# ============================================================================
# 8. Diagram Labelling Question Form
# ============================================================================

class DiagramLabellingQuestionForm(BaseQuestionForm):
    """Editor for Diagram Labelling questions with hotspot coordinates."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Diagram Asset & Callout Hotspots")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Asset path chooser
        img_row = QHBoxLayout()
        img_lbl = QLabel("Diagram Image:")
        img_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_image = QLineEdit()
        self.txt_image.setPlaceholderText("Path to diagram image file (PNG / JPEG / SVG)...")
        self.txt_image.textChanged.connect(self._on_field_changed)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._on_browse_image)
        img_row.addWidget(img_lbl)
        img_row.addWidget(self.txt_image, 1)
        img_row.addWidget(self.btn_browse)
        g_lay.addLayout(img_row)

        # Hotspots table
        h_lbl = QLabel("Hotspot Labels & Correct Terms:")
        h_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        g_lay.addWidget(h_lbl)

        btn_row = QHBoxLayout()
        self.btn_add_hotspot = QPushButton("+ Add Hotspot")
        self.btn_add_hotspot.clicked.connect(self._on_add_hotspot)
        btn_row.addWidget(self.btn_add_hotspot)
        btn_row.addStretch(1)
        g_lay.addLayout(btn_row)

        self.table_hotspots = QTableWidget(0, 5)
        self.table_hotspots.setHorizontalHeaderLabels(["Label", "X %", "Y %", "Correct Term", "Action"])
        self.table_hotspots.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_hotspots.setMaximumHeight(160)
        self.table_hotspots.cellChanged.connect(lambda r, c: self._on_field_changed())
        g_lay.addWidget(self.table_hotspots)

        self.payload_lay.addWidget(group)

    def _on_browse_image(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Diagram Image",
            "",
            "Images (*.png *.jpg *.jpeg *.svg *.webp)",
        )
        if chosen:
            self.txt_image.setText(chosen)

    def _on_add_hotspot(self) -> None:
        row = self.table_hotspots.rowCount()
        self.table_hotspots.insertRow(row)
        lbl_id = str(row + 1)
        self.table_hotspots.setItem(row, 0, QTableWidgetItem(lbl_id))
        self.table_hotspots.setItem(row, 1, QTableWidgetItem("50.0"))
        self.table_hotspots.setItem(row, 2, QTableWidgetItem("50.0"))
        self.table_hotspots.setItem(row, 3, QTableWidgetItem("Part Name"))

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda: self._on_delete_hotspot(row))
        self.table_hotspots.setCellWidget(row, 4, btn_del)
        self._on_field_changed()

    def _on_delete_hotspot(self, row_idx: int) -> None:
        self.table_hotspots.removeRow(row_idx)
        for r in range(self.table_hotspots.rowCount()):
            btn = QPushButton("Delete")
            btn.setStyleSheet("color: #DC2626;")
            btn.clicked.connect(lambda checked=False, curr=r: self._on_delete_hotspot(curr))
            self.table_hotspots.setCellWidget(r, 4, btn)
        self._on_field_changed()

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, DiagramLabellingData):
            data: DiagramLabellingData = node.type_data
            self.txt_image.setText(data.diagram_asset_path)
            self.table_hotspots.setRowCount(0)
            for h in data.hotspots:
                r = self.table_hotspots.rowCount()
                self.table_hotspots.insertRow(r)
                self.table_hotspots.setItem(r, 0, QTableWidgetItem(h.label_id))
                self.table_hotspots.setItem(r, 1, QTableWidgetItem(str(h.x_percent)))
                self.table_hotspots.setItem(r, 2, QTableWidgetItem(str(h.y_percent)))
                self.table_hotspots.setItem(r, 3, QTableWidgetItem(h.correct_term))
                btn_del = QPushButton("Delete")
                btn_del.setStyleSheet("color: #DC2626;")
                btn_del.clicked.connect(lambda checked=False, curr=r: self._on_delete_hotspot(curr))
                self.table_hotspots.setCellWidget(r, 4, btn_del)

    def _save_payload(self, node: QuestionNode) -> None:
        hotspots = []
        for r in range(self.table_hotspots.rowCount()):
            lid = self.table_hotspots.item(r, 0).text().strip() if self.table_hotspots.item(r, 0) else str(r + 1)
            x_val = float(self.table_hotspots.item(r, 1).text()) if self.table_hotspots.item(r, 1) else 50.0
            y_val = float(self.table_hotspots.item(r, 2).text()) if self.table_hotspots.item(r, 2) else 50.0
            term = self.table_hotspots.item(r, 3).text().strip() if self.table_hotspots.item(r, 3) else ""
            hotspots.append(DiagramLabelHotspot(label_id=lid, x_percent=x_val, y_percent=y_val, correct_term=term))

        node.type_data = DiagramLabellingData(
            diagram_asset_path=self.txt_image.text().strip(),
            hotspots=hotspots,
        )


# ============================================================================
# 9. Source-Based / Extract Question Form
# ============================================================================

class SourceBasedQuestionForm(BaseQuestionForm):
    """Editor for Source-based, Document, or Picture Extract stimulus questions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        group = QGroupBox("Primary Source / Document Extract")
        g_lay = QVBoxLayout(group)
        g_lay.setSpacing(8)

        # Source citation / attribution
        c_row = QHBoxLayout()
        c_lbl = QLabel("Source Attribution:")
        c_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_citation = QLineEdit()
        self.txt_citation.setPlaceholderText("e.g. Source: Megasthenes, Indika, Fragment 36; or NCERT Class 12 History")
        self.txt_citation.textChanged.connect(self._on_field_changed)
        c_row.addWidget(c_lbl)
        c_row.addWidget(self.txt_citation, 1)
        g_lay.addLayout(c_row)

        # Source excerpt editor
        s_lbl = QLabel("Source Excerpt Text / Translation:")
        s_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        g_lay.addWidget(s_lbl)
        self.editor_excerpt = RichTextEditor(placeholder="Enter primary source quotation, excerpt, or archival text...", parent=self)
        self.editor_excerpt.text_changed.connect(self._on_field_changed)
        g_lay.addWidget(self.editor_excerpt)

        self.payload_lay.addWidget(group)

    def _load_payload(self, node: QuestionNode) -> None:
        if isinstance(node.type_data, SourceBasedData):
            data: SourceBasedData = node.type_data
            self.txt_citation.setText(data.source_citation)
            self.editor_excerpt.set_html(data.source_excerpt_html)

    def _save_payload(self, node: QuestionNode) -> None:
        node.type_data = SourceBasedData(
            source_citation=self.txt_citation.text().strip(),
            source_excerpt_html=self.editor_excerpt.get_html(),
        )
