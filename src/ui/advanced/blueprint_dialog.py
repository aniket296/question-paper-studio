"""Exam Blueprint Matrix Designer, Pattern Presets & Compliance Validator Dialog.

Provides:
1. Reusable Pattern Presets (CBSE Science, JEE Main, University Semester, Unit Test).
2. Live Blueprint Target Distributions (Cognitive Bloom levels, Difficulty, Question Types).
3. Blueprint Validator Audit comparing actual paper allocation against targets.
4. One-click preset applicator configuring sections, marks, and question distributions.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.blueprint_validator import BlueprintComplianceReport, BlueprintValidator
from src.core.models.blueprint_model import (
    BlueprintTargetCell,
    ExamBlueprint,
    PatternPreset,
    SectionPresetSpec,
)
from src.core.models.enums import BloomLevel, DifficultyLevel, NumberingStyle, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import Section


def get_built_in_pattern_presets() -> List[PatternPreset]:
    """Return pre-configured standard examination pattern presets."""
    return [
        PatternPreset(
            preset_id="cbse_science_80",
            name="CBSE Class 10/12 Science (80 Marks - 3 Hours)",
            description="CBSE board structure: MCQs, Short Answer I/II, Long Answer, and Case-Based.",
            duration_minutes=180,
            max_marks=80.0,
            sections=[
                SectionPresetSpec(title="Section A (MCQs)", question_count=16, marks_per_question=1.0, default_question_type=QuestionType.MCQ),
                SectionPresetSpec(title="Section B (Very Short Answer)", question_count=5, marks_per_question=2.0, default_question_type=QuestionType.SHORT_ANSWER),
                SectionPresetSpec(title="Section C (Short Answer)", question_count=7, marks_per_question=3.0, default_question_type=QuestionType.SHORT_ANSWER),
                SectionPresetSpec(title="Section D (Long Answer)", question_count=3, marks_per_question=5.0, default_question_type=QuestionType.LONG_ANSWER),
                SectionPresetSpec(title="Section E (Case-Based)", question_count=3, marks_per_question=4.0, default_question_type=QuestionType.CASE_BASED),
            ],
        ),
        PatternPreset(
            preset_id="jee_main_100",
            name="JEE Main Pattern (100 Marks - 3 Hours)",
            description="Engineering entrance: Single-choice MCQs and Numerical Dynamic questions.",
            duration_minutes=180,
            max_marks=100.0,
            sections=[
                SectionPresetSpec(title="Section A (MCQs)", question_count=20, marks_per_question=4.0, default_question_type=QuestionType.MCQ),
                SectionPresetSpec(title="Section B (Numerical Dynamic - Attempt any 5 of 10)", question_count=10, marks_per_question=4.0, attempt_any_k=5, default_question_type=QuestionType.NUMERICAL_DYNAMIC),
            ],
        ),
        PatternPreset(
            preset_id="univ_semester_50",
            name="University Midterm / Semester Standard (50 Marks)",
            description="Higher education standard: short conceptual + descriptive analytical essays.",
            duration_minutes=120,
            max_marks=50.0,
            sections=[
                SectionPresetSpec(title="Part A (Short Conceptual)", question_count=10, marks_per_question=2.0, default_question_type=QuestionType.SHORT_ANSWER),
                SectionPresetSpec(title="Part B (Long Descriptive)", question_count=3, marks_per_question=10.0, default_question_type=QuestionType.LONG_ANSWER),
            ],
        ),
        PatternPreset(
            preset_id="unit_quiz_25",
            name="Quick Classroom Unit Test (25 Marks - 45 Mins)",
            description="Lightweight formative assessment: 5 MCQs, 5 Short Answer, 2 Long Answer.",
            duration_minutes=45,
            max_marks=25.0,
            sections=[
                SectionPresetSpec(title="Section I (Objective MCQs)", question_count=5, marks_per_question=1.0, default_question_type=QuestionType.MCQ),
                SectionPresetSpec(title="Section II (Short Answer)", question_count=5, marks_per_question=2.0, default_question_type=QuestionType.SHORT_ANSWER),
                SectionPresetSpec(title="Section III (Descriptive)", question_count=2, marks_per_question=5.0, default_question_type=QuestionType.LONG_ANSWER),
            ],
        ),
    ]


class BlueprintDialog(QDialog):
    """Exam Blueprint designer, pattern preset applicator, and compliance validation dialog."""

    preset_applied = Signal(object)  # PatternPreset
    blueprint_saved = Signal(object) # ExamBlueprint

    def __init__(
        self,
        project: ProjectState,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: ProjectState = project
        self.presets: List[PatternPreset] = get_built_in_pattern_presets()

        # Initialize or retrieve active blueprint
        if not self.project.blueprint:
            self.project.blueprint = ExamBlueprint(
                name=f"{self.project.title} Blueprint",
                total_marks_target=self.project.exam_metadata.max_marks or 100.0,
                difficulty_marks_distribution={
                    DifficultyLevel.EASY.value: 30.0,
                    DifficultyLevel.MODERATE.value: 50.0,
                    DifficultyLevel.DIFFICULT.value: 20.0,
                },
                bloom_marks_distribution={
                    BloomLevel.REMEMBER.value: 20.0,
                    BloomLevel.UNDERSTAND.value: 30.0,
                    BloomLevel.APPLY.value: 30.0,
                    BloomLevel.ANALYZE.value: 20.0,
                },
            )
        self.active_blueprint: ExamBlueprint = self.project.blueprint

        self.setWindowTitle("📐 Exam Blueprint & Pattern Preset Architect")
        self.setMinimumWidth(880)
        self.setMinimumHeight(640)

        self._build_ui()
        self._run_compliance_audit()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setSpacing(12)

        # 1. Header Banner
        lbl_title = QLabel("📐 Examination Blueprint & Pattern Presets")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0F172A;")
        root_lay.addWidget(lbl_title)

        lbl_sub = QLabel("Architect syllabus weightage, cognitive depth (Bloom's Taxonomy), and apply standardized exam presets.")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 9.5pt;")
        root_lay.addWidget(lbl_sub)

        # 2. Pattern Preset Selector Row
        preset_box = QGroupBox("Standard Examination Pattern Presets")
        pr_lay = QHBoxLayout(preset_box)
        pr_lay.setSpacing(10)

        self.combo_presets = QComboBox()
        for p in self.presets:
            self.combo_presets.addItem(f"{p.name} ({p.max_marks:g} M)", p)
        pr_lay.addWidget(QLabel("Preset:"))
        pr_lay.addWidget(self.combo_presets, 1)

        self.btn_apply_preset = QPushButton("🚀 Apply Preset to Paper")
        self.btn_apply_preset.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: 700; padding: 6px 14px;")
        self.btn_apply_preset.clicked.connect(self._on_apply_preset)
        pr_lay.addWidget(self.btn_apply_preset)

        root_lay.addWidget(preset_box)

        # 3. Main Multi-Tab Matrix
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-weight: 600; padding: 6px 14px; }")

        # Tab 1: Blueprint Target Distributions
        self.tab_targets = QWidget()
        t_lay = QVBoxLayout(self.tab_targets)
        t_lay.setContentsMargins(10, 10, 10, 10)
        t_lay.setSpacing(8)

        # Total target marks row
        tot_row = QHBoxLayout()
        tot_lbl = QLabel("Total Paper Target Marks:")
        tot_lbl.setStyleSheet("font-weight: 700; color: #1E293B;")
        self.spin_total_target = QDoubleSpinBox()
        self.spin_total_target.setRange(5.0, 500.0)
        self.spin_total_target.setValue(self.active_blueprint.total_marks_target)
        self.spin_total_target.setSuffix(" M")
        self.spin_total_target.valueChanged.connect(self._on_target_changed)
        tot_row.addWidget(tot_lbl)
        tot_row.addWidget(self.spin_total_target)
        tot_row.addStretch(1)
        t_lay.addLayout(tot_row)

        # Difficulty & Bloom Tables side-by-side
        split_box = QHBoxLayout()

        # Difficulty Table
        diff_box = QGroupBox("Difficulty Distribution Targets")
        d_lay = QVBoxLayout(diff_box)
        self.table_diff = QTableWidget(3, 2)
        self.table_diff.setHorizontalHeaderLabels(["Difficulty Level", "Target Marks"])
        self.table_diff.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for idx, d in enumerate([DifficultyLevel.EASY, DifficultyLevel.MODERATE, DifficultyLevel.DIFFICULT]):
            self.table_diff.setItem(idx, 0, QTableWidgetItem(d.value))
            val = self.active_blueprint.difficulty_marks_distribution.get(d.value, 0.0)
            self.table_diff.setItem(idx, 1, QTableWidgetItem(f"{val:g}"))
        self.table_diff.cellChanged.connect(lambda r, c: self._on_target_changed())
        d_lay.addWidget(self.table_diff)
        split_box.addWidget(diff_box)

        # Bloom Table
        bloom_box = QGroupBox("Bloom's Cognitive Taxonomy Targets")
        b_lay = QVBoxLayout(bloom_box)
        bloom_levels = list(BloomLevel)
        self.table_bloom = QTableWidget(len(bloom_levels), 2)
        self.table_bloom.setHorizontalHeaderLabels(["Cognitive Level", "Target Marks"])
        self.table_bloom.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for idx, bl in enumerate(bloom_levels):
            self.table_bloom.setItem(idx, 0, QTableWidgetItem(bl.value))
            val = self.active_blueprint.bloom_marks_distribution.get(bl.value, 0.0)
            self.table_bloom.setItem(idx, 1, QTableWidgetItem(f"{val:g}"))
        self.table_bloom.cellChanged.connect(lambda r, c: self._on_target_changed())
        b_lay.addWidget(self.table_bloom)
        split_box.addWidget(bloom_box)

        t_lay.addLayout(split_box)
        self.tabs.addTab(self.tab_targets, "📐 Target Weightage Distributions")

        # Tab 2: Compliance Validation Audit Report
        self.tab_audit = QWidget()
        aud_lay = QVBoxLayout(self.tab_audit)
        aud_lay.setContentsMargins(10, 10, 10, 10)
        aud_lay.setSpacing(8)

        self.lbl_audit_status = QLabel("Audit Status: Pending")
        self.lbl_audit_status.setStyleSheet("font-size: 11pt; font-weight: 700; color: #1E293B;")
        aud_lay.addWidget(self.lbl_audit_status)

        self.table_variance = QTableWidget(0, 5)
        self.table_variance.setHorizontalHeaderLabels(["Dimension", "Category", "Target", "Actual", "Compliance"])
        self.table_variance.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_variance.setAlternatingRowColors(True)
        aud_lay.addWidget(self.table_variance, 1)

        btn_recheck = QPushButton("🔄 Re-Validate Against Paper")
        btn_recheck.clicked.connect(self._run_compliance_audit)
        aud_lay.addWidget(btn_recheck)

        self.tabs.addTab(self.tab_audit, "✓ Compliance & Validation Audit")
        root_lay.addWidget(self.tabs, 1)

        # 4. Dialog Button Box
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        root_lay.addLayout(btn_box)

    def _on_target_changed(self) -> None:
        self.active_blueprint.total_marks_target = self.spin_total_target.value()

        # Update difficulty targets
        for r in range(self.table_diff.rowCount()):
            lvl_item = self.table_diff.item(r, 0)
            val_item = self.table_diff.item(r, 1)
            if lvl_item and val_item:
                try:
                    self.active_blueprint.difficulty_marks_distribution[lvl_item.text()] = float(val_item.text())
                except ValueError:
                    pass

        # Update bloom targets
        for r in range(self.table_bloom.rowCount()):
            lvl_item = self.table_bloom.item(r, 0)
            val_item = self.table_bloom.item(r, 1)
            if lvl_item and val_item:
                try:
                    self.active_blueprint.bloom_marks_distribution[lvl_item.text()] = float(val_item.text())
                except ValueError:
                    pass

        self.blueprint_saved.emit(self.active_blueprint)

    def _on_apply_preset(self) -> None:
        preset: PatternPreset = self.combo_presets.currentData()
        if not preset:
            return

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            ans = QMessageBox.question(
                self,
                "Apply Exam Pattern Preset",
                f"Applying preset '{preset.name}' will configure {len(preset.sections)} sections and "
                f"populate question slots totaling {preset.max_marks:g} marks.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        # Apply preset to project
        self.project.exam_metadata.max_marks = preset.max_marks
        self.project.exam_metadata.duration_minutes = preset.duration_minutes
        self.project.sections.clear()

        for sec_spec in preset.sections:
            new_sec = Section(
                title=sec_spec.title,
                instructions_html=sec_spec.instructions_html,
                attempt_any_k=sec_spec.attempt_any_k,
                section_numbering_style=sec_spec.numbering_style,
            )
            for q_i in range(sec_spec.question_count):
                q_node = QuestionNode(
                    question_type=sec_spec.default_question_type,
                    prompt_html=f"<p>[{sec_spec.title}] Question statement {q_i + 1}...</p>",
                    marks=sec_spec.marks_per_question,
                )
                new_sec.questions.append(q_node)
            self.project.sections.append(new_sec)

        self.active_blueprint.total_marks_target = preset.max_marks
        self.spin_total_target.setValue(preset.max_marks)

        self.preset_applied.emit(preset)
        self._run_compliance_audit()
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            QMessageBox.information(self, "Preset Applied", f"Successfully structured paper with {len(preset.sections)} section(s).")

    def _run_compliance_audit(self) -> None:
        rep: BlueprintComplianceReport = BlueprintValidator.validate_project(
            self.project,
            blueprint=self.active_blueprint,
            tolerance_marks=1.0,
        )

        if rep.overall_compliant:
            self.lbl_audit_status.setText(f"✓ 100% Compliant with Blueprint '{rep.blueprint_name}' (Target: {rep.target_total_marks:g} M, Actual: {rep.actual_total_marks:g} M)")
            self.lbl_audit_status.setStyleSheet("font-size: 11pt; font-weight: 700; color: #16A34A;")
        else:
            self.lbl_audit_status.setText(f"⚠ Non-Compliant: Target {rep.target_total_marks:g} M vs Actual {rep.actual_total_marks:g} M")
            self.lbl_audit_status.setStyleSheet("font-size: 11pt; font-weight: 700; color: #DC2626;")

        all_variances = []
        for v in rep.difficulty_variances:
            all_variances.append(("Difficulty", v))
        for v in rep.bloom_variances:
            all_variances.append(("Bloom Taxonomy", v))
        for v in rep.question_type_variances:
            all_variances.append(("Question Type", v))
        for v in rep.topic_variances:
            all_variances.append(("Topic", v))

        self.table_variance.setRowCount(len(all_variances))
        for r_idx, (dim_name, v) in enumerate(all_variances):
            self.table_variance.setItem(r_idx, 0, QTableWidgetItem(dim_name))
            self.table_variance.setItem(r_idx, 1, QTableWidgetItem(v.category.title()))
            self.table_variance.setItem(r_idx, 2, QTableWidgetItem(f"{v.target_marks:g} M"))
            self.table_variance.setItem(r_idx, 3, QTableWidgetItem(f"{v.actual_marks:g} M"))

            status_str = "✓ Compliant" if v.is_compliant else f"⚠ Diff {v.variance_marks:+g} M"
            item = QTableWidgetItem(status_str)
            item.setForeground(Qt.GlobalColor.darkGreen if v.is_compliant else Qt.GlobalColor.darkRed)
            self.table_variance.setItem(r_idx, 4, item)
