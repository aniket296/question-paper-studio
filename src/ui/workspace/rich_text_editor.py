"""WYSIWYG Rich Text Editor with Formatting Toolbar, LaTeX Inserter, and Math Symbols."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
    QTextTableFormat,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SYMBOLS_JSON_PATH = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "math" / "symbols.json"


class LatexInputDialog(QDialog):
    """Dialog allowing the teacher to input LaTeX math expressions with live equation preview."""

    def __init__(self, initial_latex: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Mathematical Formula (LaTeX)")
        self.resize(460, 260)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        info = QLabel(
            "Enter standard LaTeX equation syntax.\n"
            "Examples: \\frac{a}{b}, \\sqrt{x^2 + y^2}, \\int_{0}^{\\pi} \\sin(x)dx, E = mc^2"
        )
        info.setStyleSheet("color: #475569; font-size: 9.5pt;")
        lay.addWidget(info)

        self.txt_latex = QPlainTextEdit()
        self.txt_latex.setPlaceholderText("\\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}")
        self.txt_latex.setPlainText(initial_latex)
        cur = self.txt_latex.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.txt_latex.setTextCursor(cur)
        lay.addWidget(self.txt_latex, 1)

        # Quick Math Symbol Shortcuts
        quick_bar = QHBoxLayout()
        quick_symbols = ["\\frac{a}{b}", "\\sqrt{x}", "x^2", "x_i", "\\pm", "\\times", "\\div", "\\le", "\\ge", "\\alpha", "\\theta", "\\pi", "\\Delta", "\\int"]
        for sym in quick_symbols:
            btn = QPushButton(sym)
            btn.setMaximumHeight(24)
            btn.clicked.connect(lambda _, s=sym: self._insert_snippet(s))
            quick_bar.addWidget(btn)
        lay.addLayout(quick_bar)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _insert_snippet(self, snippet: str) -> None:
        self.txt_latex.insertPlainText(snippet)
        self.txt_latex.setFocus()

    def get_latex(self) -> str:
        return self.txt_latex.toPlainText().strip()


class SymbolPickerDialog(QDialog):
    """Categorized dialog displaying mathematical symbols, Greek letters, and arrows."""

    symbol_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Mathematical & Scientific Symbol")
        self.resize(520, 360)
        self.setModal(True)

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        self._load_symbols()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignRight)

    def _load_symbols(self) -> None:
        symbols_data = {}
        if SYMBOLS_JSON_PATH.exists():
            try:
                symbols_data = json.loads(SYMBOLS_JSON_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not symbols_data:
            symbols_data = {
                "greek": ["α", "β", "γ", "δ", "ε", "θ", "λ", "μ", "π", "σ", "φ", "ω", "Δ", "Σ", "Ω"],
                "operators": ["±", "×", "÷", "≠", "≈", "≤", "≥", "∞", "√", "∛", "∫", "∮", "∂", "∇"],
                "sets_arrows": ["∈", "∉", "⊂", "⊆", "∪", "∩", "∅", "→", "←", "↔", "⇒", "⇔", "∴", "∵"],
            }

        for cat_name, symbols in symbols_data.items():
            tab_widget = QWidget()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            grid_content = QWidget()
            grid_lay = QGridLayout(grid_content)
            grid_lay.setSpacing(6)

            cols = 8
            for idx, sym in enumerate(symbols):
                btn = QPushButton(sym)
                btn.setFixedSize(48, 38)
                btn.setStyleSheet("font-size: 14pt; font-family: 'Noto Sans', sans-serif; font-weight: 600;")
                btn.clicked.connect(lambda _, s=sym: self._on_symbol_clicked(s))
                r, c = divmod(idx, cols)
                grid_lay.addWidget(btn, r, c)

            grid_lay.setRowStretch(len(symbols) // cols + 1, 1)
            scroll.setWidget(grid_content)

            tab_lay = QVBoxLayout(tab_widget)
            tab_lay.setContentsMargins(4, 4, 4, 4)
            tab_lay.addWidget(scroll)

            display_name = cat_name.replace("_", " ").title()
            self.tabs.addTab(tab_widget, display_name)

    def _on_symbol_clicked(self, symbol: str) -> None:
        self.symbol_selected.emit(symbol)
        self.accept()


class TableInsertDialog(QDialog):
    """Dialog prompting for row and column counts when inserting a table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Table")
        self.setFixedSize(260, 150)
        self.setModal(True)

        lay = QVBoxLayout(self)
        grid = QGridLayout()

        grid.addWidget(QLabel("Rows:"), 0, 0)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 20)
        self.spin_rows.setValue(3)
        grid.addWidget(self.spin_rows, 0, 1)

        grid.addWidget(QLabel("Columns:"), 1, 0)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 10)
        self.spin_cols.setValue(3)
        grid.addWidget(self.spin_cols, 1, 1)

        lay.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def get_dimensions(self) -> tuple[int, int]:
        return self.spin_rows.value(), self.spin_cols.value()


class RichTextEditor(QWidget):
    """Self-contained WYSIWYG rich text editor with full formatting toolbar, math formulas, and symbols."""

    text_changed = Signal()

    def __init__(self, placeholder: str = "Type question statement here...", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._block_signals = False
        self._build_ui(placeholder)

    def _build_ui(self, placeholder: str) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(4)

        # 1. Formatting Toolbar Frame
        tb_frame = QFrame()
        tb_frame.setObjectName("CardFrame")
        tb_frame.setStyleSheet(
            "#CardFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 2px; }"
        )
        tb_lay = QHBoxLayout(tb_frame)
        tb_lay.setContentsMargins(4, 2, 4, 2)
        tb_lay.setSpacing(4)

        # Font Family
        self.combo_font = QFontComboBox()
        self.combo_font.setMaximumWidth(130)
        self.combo_font.setCurrentFont(QFont("Noto Sans"))
        self.combo_font.currentFontChanged.connect(self._on_font_family_changed)
        tb_lay.addWidget(self.combo_font)

        # Font Size
        self.combo_size = QComboBox()
        self.combo_size.setEditable(True)
        self.combo_size.setMaximumWidth(55)
        for s in [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28]:
            self.combo_size.addItem(str(s))
        self.combo_size.setCurrentText("11")
        self.combo_size.currentTextChanged.connect(self._on_font_size_changed)
        tb_lay.addWidget(self.combo_size)

        tb_lay.addSpacing(4)

        # Bold, Italic, Underline
        self.btn_bold = QToolButton()
        self.btn_bold.setText("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setStyleSheet("font-weight: 800; font-family: serif;")
        self.btn_bold.setToolTip("Bold (Ctrl+B)")
        self.btn_bold.clicked.connect(self._toggle_bold)
        tb_lay.addWidget(self.btn_bold)

        self.btn_italic = QToolButton()
        self.btn_italic.setText("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style: italic; font-family: serif;")
        self.btn_italic.setToolTip("Italic (Ctrl+I)")
        self.btn_italic.clicked.connect(self._toggle_italic)
        tb_lay.addWidget(self.btn_italic)

        self.btn_underline = QToolButton()
        self.btn_underline.setText("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setStyleSheet("text-decoration: underline;")
        self.btn_underline.setToolTip("Underline (Ctrl+U)")
        self.btn_underline.clicked.connect(self._toggle_underline)
        tb_lay.addWidget(self.btn_underline)

        # Subscript & Superscript
        self.btn_sub = QToolButton()
        self.btn_sub.setText("X₂")
        self.btn_sub.setCheckable(True)
        self.btn_sub.setToolTip("Subscript")
        self.btn_sub.clicked.connect(self._toggle_subscript)
        tb_lay.addWidget(self.btn_sub)

        self.btn_super = QToolButton()
        self.btn_super.setText("X²")
        self.btn_super.setCheckable(True)
        self.btn_super.setToolTip("Superscript")
        self.btn_super.clicked.connect(self._toggle_superscript)
        tb_lay.addWidget(self.btn_super)

        tb_lay.addSpacing(4)

        # Alignments
        self.btn_align_left = QToolButton()
        self.btn_align_left.setText("⇤")
        self.btn_align_left.setToolTip("Align Left")
        self.btn_align_left.clicked.connect(lambda: self.txt_edit.setAlignment(Qt.AlignmentFlag.AlignLeft))
        tb_lay.addWidget(self.btn_align_left)

        self.btn_align_center = QToolButton()
        self.btn_align_center.setText("⇥⇤")
        self.btn_align_center.setToolTip("Align Center")
        self.btn_align_center.clicked.connect(lambda: self.txt_edit.setAlignment(Qt.AlignmentFlag.AlignCenter))
        tb_lay.addWidget(self.btn_align_center)

        self.btn_align_right = QToolButton()
        self.btn_align_right.setText("⇥")
        self.btn_align_right.setToolTip("Align Right")
        self.btn_align_right.clicked.connect(lambda: self.txt_edit.setAlignment(Qt.AlignmentFlag.AlignRight))
        tb_lay.addWidget(self.btn_align_right)

        tb_lay.addSpacing(4)

        # Color picker
        self.btn_color = QToolButton()
        self.btn_color.setText("🎨")
        self.btn_color.setToolTip("Text Color")
        self.btn_color.clicked.connect(self._choose_text_color)
        tb_lay.addWidget(self.btn_color)

        # Lists
        self.btn_bullet = QToolButton()
        self.btn_bullet.setText("• List")
        self.btn_bullet.setToolTip("Bullet List")
        self.btn_bullet.clicked.connect(self._insert_bullet_list)
        tb_lay.addWidget(self.btn_bullet)

        self.btn_number = QToolButton()
        self.btn_number.setText("1. List")
        self.btn_number.setToolTip("Numbered List")
        self.btn_number.clicked.connect(self._insert_numbered_list)
        tb_lay.addWidget(self.btn_number)

        tb_lay.addStretch(1)

        # Specialized Educational Inserters
        self.btn_formula = QPushButton("∑ Formula")
        self.btn_formula.setToolTip("Insert LaTeX Equation")
        self.btn_formula.clicked.connect(self._on_insert_formula)
        tb_lay.addWidget(self.btn_formula)

        self.btn_symbol = QPushButton("Ω Symbol")
        self.btn_symbol.setToolTip("Insert Mathematical Symbol")
        self.btn_symbol.clicked.connect(self._on_insert_symbol)
        tb_lay.addWidget(self.btn_symbol)

        self.btn_table = QPushButton("⊞ Table")
        self.btn_table.setToolTip("Insert Table")
        self.btn_table.clicked.connect(self._on_insert_table)
        tb_lay.addWidget(self.btn_table)

        self.btn_image = QPushButton("🖼 Image")
        self.btn_image.setToolTip("Insert Diagram / Image")
        self.btn_image.clicked.connect(self._on_insert_image)
        tb_lay.addWidget(self.btn_image)

        root_lay.addWidget(tb_frame)

        # 2. Rich Text Edit Area
        self.txt_edit = QTextEdit()
        self.txt_edit.setPlaceholderText(placeholder)
        self.txt_edit.setAcceptRichText(True)
        self.txt_edit.cursorPositionChanged.connect(self._update_format_buttons_state)
        self.txt_edit.textChanged.connect(self._on_text_changed)
        root_lay.addWidget(self.txt_edit, 1)

    # ========================================================================
    # Text Formatting Handlers
    # ========================================================================

    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self.btn_bold.isChecked() else QFont.Weight.Normal)
        self._merge_format_on_selection(fmt)

    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.btn_italic.isChecked())
        self._merge_format_on_selection(fmt)

    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.btn_underline.isChecked())
        self._merge_format_on_selection(fmt)

    def _toggle_subscript(self) -> None:
        fmt = QTextCharFormat()
        if self.btn_sub.isChecked():
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
            self.btn_super.setChecked(False)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        self._merge_format_on_selection(fmt)

    def _toggle_superscript(self) -> None:
        fmt = QTextCharFormat()
        if self.btn_super.isChecked():
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
            self.btn_sub.setChecked(False)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        self._merge_format_on_selection(fmt)

    def _on_font_family_changed(self, font: QFont) -> None:
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self._merge_format_on_selection(fmt)

    def _on_font_size_changed(self, size_text: str) -> None:
        try:
            pt = float(size_text)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(pt)
            self._merge_format_on_selection(fmt)
        except ValueError:
            pass

    def _choose_text_color(self) -> None:
        col = QColorDialog.getColor(QColor("#000000"), self, "Select Text Color")
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(col)
            self._merge_format_on_selection(fmt)

    def _merge_format_on_selection(self, fmt: QTextCharFormat) -> None:
        cursor = self.txt_edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.txt_edit.mergeCurrentCharFormat(fmt)
        self.txt_edit.setFocus()

    def _update_format_buttons_state(self) -> None:
        cursor = self.txt_edit.textCursor()
        fmt = cursor.charFormat()
        self.btn_bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_underline.setChecked(fmt.fontUnderline())
        valign = fmt.verticalAlignment()
        self.btn_sub.setChecked(valign == QTextCharFormat.VerticalAlignment.AlignSubScript)
        self.btn_super.setChecked(valign == QTextCharFormat.VerticalAlignment.AlignSuperScript)

    def _insert_bullet_list(self) -> None:
        cursor = self.txt_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDisc)

    def _insert_numbered_list(self) -> None:
        cursor = self.txt_edit.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDecimal)

    # ========================================================================
    # Inserters (Math, Symbols, Tables, Images)
    # ========================================================================

    def _on_insert_formula(self) -> None:
        dlg = LatexInputDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            latex = dlg.get_latex()
            if latex:
                # Insert formula enclosed in standard math delimiters
                formula_html = f'<span class="math-tex">\\({latex}\\)</span>'
                self.txt_edit.insertHtml(formula_html)

    def _on_insert_symbol(self) -> None:
        dlg = SymbolPickerDialog(parent=self)
        dlg.symbol_selected.connect(lambda sym: self.txt_edit.insertPlainText(sym))
        dlg.exec()

    def _on_insert_table(self) -> None:
        dlg = TableInsertDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rows, cols = dlg.get_dimensions()
            cursor = self.txt_edit.textCursor()
            tbl_fmt = QTextTableFormat()
            tbl_fmt.setBorder(1.0)
            tbl_fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
            tbl_fmt.setCellPadding(4)
            tbl_fmt.setCellSpacing(0)
            cursor.insertTable(rows, cols, tbl_fmt)

    def _on_insert_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Insert Image / Diagram",
            "",
            "Images (*.png *.jpg *.jpeg *.svg)",
        )
        if path:
            file_url = Path(path).as_uri()
            img_html = f'<p style="text-align: center;"><img src="{file_url}" style="max-width: 80%; height: auto;" /></p>'
            self.txt_edit.insertHtml(img_html)

    # ========================================================================
    # Data Accessors
    # ========================================================================

    def get_html(self) -> str:
        """Return the current document formatted as HTML."""
        return self.txt_edit.toHtml().strip()

    def get_plain_text(self) -> str:
        """Return raw unformatted text."""
        return self.txt_edit.toPlainText().strip()

    def set_html(self, html: str) -> None:
        """Set document content from HTML without triggering external signals."""
        self._block_signals = True
        try:
            self.txt_edit.setHtml(html or "")
        finally:
            self._block_signals = False

    def _on_text_changed(self) -> None:
        if not self._block_signals:
            self.text_changed.emit()
