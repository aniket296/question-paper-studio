"""Collapsible Examination Metadata & General Instructions Header Bar."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.models.project_model import ExamMetadata, ProjectState


class ExamInfoBar(QWidget):
    """Collapsible examination header bar allowing live editing of title, metadata, and instructions."""

    metadata_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._is_expanded = False
        self._block_signals = False
        self._build_ui()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Main Card Frame
        self.frame = QFrame()
        self.frame.setObjectName("CardFrame")
        self.frame.setStyleSheet(
            "#CardFrame { background-color: #FFFFFF; border-bottom: 1px solid #E2E8F0; padding: 6px; }"
        )
        frame_lay = QVBoxLayout(self.frame)
        frame_lay.setContentsMargins(10, 6, 10, 6)
        frame_lay.setSpacing(6)

        # 1. Compact Bar (Always Visible)
        compact_row = QHBoxLayout()
        compact_row.setSpacing(8)

        # Paper Title
        title_lbl = QLabel("Title:")
        title_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("Question Paper Title (e.g. Mid-Term Examination 2026)")
        self.edit_title.textChanged.connect(self._on_field_changed)
        compact_row.addWidget(title_lbl)
        compact_row.addWidget(self.edit_title, 3)

        # Subject Name
        subj_lbl = QLabel("Subject:")
        subj_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_subject = QLineEdit()
        self.edit_subject.setPlaceholderText("Subject (e.g. Physics)")
        self.edit_subject.textChanged.connect(self._on_field_changed)
        compact_row.addWidget(subj_lbl)
        compact_row.addWidget(self.edit_subject, 2)

        # Class / Semester
        class_lbl = QLabel("Class:")
        class_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_class = QLineEdit()
        self.edit_class.setPlaceholderText("Class / Grade")
        self.edit_class.setMaximumWidth(110)
        self.edit_class.textChanged.connect(self._on_field_changed)
        compact_row.addWidget(class_lbl)
        compact_row.addWidget(self.edit_class, 1)

        # Duration
        dur_lbl = QLabel("Duration:")
        dur_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(5, 720)
        self.spin_duration.setValue(180)
        self.spin_duration.setSuffix(" min")
        self.spin_duration.valueChanged.connect(self._on_field_changed)
        compact_row.addWidget(dur_lbl)
        compact_row.addWidget(self.spin_duration)

        # Max Marks
        marks_lbl = QLabel("Max Marks:")
        marks_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.spin_max_marks = QDoubleSpinBox()
        self.spin_max_marks.setRange(0.0, 1000.0)
        self.spin_max_marks.setDecimals(1)
        self.spin_max_marks.setValue(100.0)
        self.spin_max_marks.valueChanged.connect(self._on_field_changed)
        compact_row.addWidget(marks_lbl)
        compact_row.addWidget(self.spin_max_marks)

        # Toggle Expand Button
        self.btn_toggle_expand = QPushButton("▼ More Details")
        self.btn_toggle_expand.setCheckable(True)
        self.btn_toggle_expand.clicked.connect(self.toggle_expanded)
        compact_row.addWidget(self.btn_toggle_expand)

        frame_lay.addLayout(compact_row)

        # 2. Collapsible Expanded Drawer (Hidden by default)
        self.drawer_widget = QWidget()
        drawer_lay = QGridLayout(self.drawer_widget)
        drawer_lay.setContentsMargins(0, 6, 0, 0)
        drawer_lay.setSpacing(8)

        # Subject Code
        code_lbl = QLabel("Subject Code:")
        code_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_subject_code = QLineEdit()
        self.edit_subject_code.setPlaceholderText("e.g. PHY-101 / 042")
        self.edit_subject_code.textChanged.connect(self._on_field_changed)
        drawer_lay.addWidget(code_lbl, 0, 0)
        drawer_lay.addWidget(self.edit_subject_code, 0, 1)

        # Exam Date
        date_lbl = QLabel("Exam Date:")
        date_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_exam_date = QLineEdit()
        self.edit_exam_date.setPlaceholderText("e.g. 15 March 2026")
        self.edit_exam_date.textChanged.connect(self._on_field_changed)
        drawer_lay.addWidget(date_lbl, 0, 2)
        drawer_lay.addWidget(self.edit_exam_date, 0, 3)

        # Set Identifier
        set_lbl = QLabel("Set Identifier:")
        set_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.edit_set_identifier = QLineEdit()
        self.edit_set_identifier.setPlaceholderText("e.g. Set A (leave blank for single set)")
        self.edit_set_identifier.textChanged.connect(self._on_field_changed)
        drawer_lay.addWidget(set_lbl, 0, 4)
        drawer_lay.addWidget(self.edit_set_identifier, 0, 5)

        # General Instructions Editor
        inst_lbl = QLabel("General Instructions:")
        inst_lbl.setStyleSheet("font-weight: 600; color: #475569;")
        self.txt_instructions = QPlainTextEdit()
        self.txt_instructions.setPlaceholderText(
            "1. All questions are compulsory.\n"
            "2. The question paper contains three sections.\n"
            "3. Use of calculators is not permitted."
        )
        self.txt_instructions.setMaximumHeight(80)
        self.txt_instructions.textChanged.connect(self._on_field_changed)
        drawer_lay.addWidget(inst_lbl, 1, 0, Qt.AlignmentFlag.AlignTop)
        drawer_lay.addWidget(self.txt_instructions, 1, 1, 1, 5)

        self.drawer_widget.setVisible(False)
        frame_lay.addWidget(self.drawer_widget)

        root_lay.addWidget(self.frame)

    def toggle_expanded(self) -> None:
        """Toggle the collapsible expanded drawer."""
        self._is_expanded = not self._is_expanded
        self.drawer_widget.setVisible(self._is_expanded)
        self.btn_toggle_expand.setText("▲ Less Details" if self._is_expanded else "▼ More Details")
        self.btn_toggle_expand.setChecked(self._is_expanded)

    def load_from_project(self, project: ProjectState) -> None:
        """Populate fields from `project` metadata without emitting unnecessary change signals."""
        self._block_signals = True
        try:
            self.edit_title.setText(project.title)
            meta = project.exam_metadata
            self.edit_subject.setText(meta.subject_name)
            self.edit_class.setText(meta.class_semester)
            self.spin_duration.setValue(meta.duration_minutes or 180)
            self.spin_max_marks.setValue(meta.max_marks if meta.max_marks is not None else 100.0)
            self.edit_subject_code.setText(meta.subject_code)
            self.edit_exam_date.setText(meta.exam_date)
            self.edit_set_identifier.setText(meta.set_identifier)
            self.txt_instructions.setPlainText(meta.general_instructions)
        finally:
            self._block_signals = False

    def save_to_project(self, project: ProjectState) -> None:
        """Save form field values into `project`."""
        title = self.edit_title.text().strip()
        if title:
            project.title = title

        meta = project.exam_metadata
        meta.exam_name = title
        meta.subject_name = self.edit_subject.text().strip()
        meta.class_semester = self.edit_class.text().strip()
        meta.duration_minutes = int(self.spin_duration.value())
        meta.max_marks = float(self.spin_max_marks.value())
        meta.subject_code = self.edit_subject_code.text().strip()
        meta.exam_date = self.edit_exam_date.text().strip()
        meta.set_identifier = self.edit_set_identifier.text().strip()
        meta.general_instructions = self.txt_instructions.toPlainText().strip()

    def _on_field_changed(self) -> None:
        if not self._block_signals:
            self.metadata_changed.emit()
