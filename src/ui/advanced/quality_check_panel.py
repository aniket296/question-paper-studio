"""Quality & Integrity Audit Panel for Question Paper Studio.

Runs automated heuristic audits:
1. Duplicate question prompts and duplicate MCQ option values.
2. Missing correct answer keys across MCQs, blanks, and match the pair.
3. Formatting anomalies and unclosed math delimiters.
4. Marks allocation discrepancies and parent-child sum deduplication.
5. Overall Paper Health Score (0 - 100%) and jump-to-question navigation.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.quality_checker import (
    QualityAuditReport,
    QualityChecker,
    QualityIssue,
    QualitySeverity,
)
from src.core.models.project_model import ProjectState


class QualityCheckPanel(QDialog):
    """Quality and compliance inspection dialog reporting health score and defects."""

    navigate_to_question = Signal(str)  # question_id

    def __init__(
        self,
        project: ProjectState,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: ProjectState = project
        self.audit_report: Optional[QualityAuditReport] = None

        self.setWindowTitle("🔍 Question Paper Quality & Integrity Audit")
        self.setMinimumWidth(820)
        self.setMinimumHeight(520)

        self._build_ui()
        self.run_audit()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setSpacing(12)

        # 1. Header Banner & Health Score Card
        self.card_score = QFrame()
        self.card_score.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;"
        )
        c_lay = QHBoxLayout(self.card_score)
        c_lay.setContentsMargins(12, 8, 12, 8)

        score_box = QVBoxLayout()
        self.lbl_score_val = QLabel("Paper Health Score: -- / 100")
        self.lbl_score_val.setStyleSheet("font-size: 16pt; font-weight: 800; color: #2563EB;")
        self.lbl_score_desc = QLabel("Auditing paper structure and answer key integrity...")
        self.lbl_score_desc.setStyleSheet("color: #64748B; font-size: 10pt;")
        score_box.addWidget(self.lbl_score_val)
        score_box.addWidget(self.lbl_score_desc)
        c_lay.addLayout(score_box, 1)

        # Counter badges
        self.lbl_critical = QLabel("0 Critical")
        self.lbl_critical.setStyleSheet(
            "background-color: #FEE2E2; color: #DC2626; font-weight: 700; padding: 6px 12px; border-radius: 6px;"
        )
        self.lbl_warnings = QLabel("0 Warnings")
        self.lbl_warnings.setStyleSheet(
            "background-color: #FEF3C7; color: #D97706; font-weight: 700; padding: 6px 12px; border-radius: 6px;"
        )
        self.lbl_info = QLabel("0 Notices")
        self.lbl_info.setStyleSheet(
            "background-color: #E0F2FE; color: #0284C7; font-weight: 700; padding: 6px 12px; border-radius: 6px;"
        )

        c_lay.addWidget(self.lbl_critical)
        c_lay.addWidget(self.lbl_warnings)
        c_lay.addWidget(self.lbl_info)
        root_lay.addWidget(self.card_score)

        # 2. Issues List Table
        issue_box = QGroupBox("Detected Defects, Ambiguities & Formatting Notices")
        i_lay = QVBoxLayout(issue_box)
        i_lay.setSpacing(8)

        self.table_issues = QTableWidget(0, 4)
        self.table_issues.setHorizontalHeaderLabels(["Severity", "Q#", "Code", "Description & Recommendations"])
        self.table_issues.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_issues.setAlternatingRowColors(True)
        self.table_issues.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_issues.itemDoubleClicked.connect(self._on_row_double_clicked)
        i_lay.addWidget(self.table_issues, 1)

        # Table action strip
        tb_strip = QHBoxLayout()
        self.btn_jump = QPushButton("🎯 Jump to Selected Question in Paper")
        self.btn_jump.setEnabled(False)
        self.btn_jump.clicked.connect(self._on_jump_to_question)
        self.table_issues.itemSelectionChanged.connect(
            lambda: self.btn_jump.setEnabled(self.table_issues.currentRow() >= 0)
        )
        tb_strip.addWidget(self.btn_jump)
        tb_strip.addStretch(1)

        self.btn_recheck = QPushButton("🔄 Re-Audit Paper")
        self.btn_recheck.clicked.connect(self.run_audit)
        tb_strip.addWidget(self.btn_recheck)

        i_lay.addLayout(tb_strip)
        root_lay.addWidget(issue_box, 1)

        # 3. Dialog Button Box
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        root_lay.addLayout(btn_box)

    def run_audit(self) -> QualityAuditReport:
        """Execute heuristic quality evaluation and refresh UI cards and table."""
        report = QualityChecker.audit_project(self.project)
        self.audit_report = report

        # Compute composite Health Score (100 base - critical*25 - warning*5)
        raw_score = 100 - (report.critical_count * 25 + report.warning_count * 5)
        health_score = max(0, min(100, raw_score))

        # Update counter badges
        self.lbl_critical.setText(f"{report.critical_count} Critical")
        self.lbl_warnings.setText(f"{report.warning_count} Warnings")
        self.lbl_info.setText(f"{report.info_count} Notices")

        # Update score banner
        self.lbl_score_val.setText(f"Paper Health Score: {health_score} / 100")
        if health_score >= 90:
            self.lbl_score_val.setStyleSheet("font-size: 16pt; font-weight: 800; color: #16A34A;")
            self.lbl_score_desc.setText("✓ High Quality — Exam paper is publication-ready with clean structure.")
        elif health_score >= 70:
            self.lbl_score_val.setStyleSheet("font-size: 16pt; font-weight: 800; color: #D97706;")
            self.lbl_score_desc.setText("⚠ Review Advised — Minor formatting or option balance issues detected.")
        else:
            self.lbl_score_val.setStyleSheet("font-size: 16pt; font-weight: 800; color: #DC2626;")
            self.lbl_score_desc.setText("✗ Action Required — Critical issues found (e.g. missing answer keys or empty prompts).")

        # Populate issues table
        self.table_issues.setRowCount(len(report.issues))
        for r_idx, issue in enumerate(report.issues):
            # Severity item
            sev_item = QTableWidgetItem(issue.severity.value)
            if issue.severity == QualitySeverity.CRITICAL:
                sev_item.setForeground(Qt.GlobalColor.darkRed)
            elif issue.severity == QualitySeverity.WARNING:
                sev_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                sev_item.setForeground(Qt.GlobalColor.darkBlue)
            self.table_issues.setItem(r_idx, 0, sev_item)

            # Question number
            q_str = issue.resolved_number or "Paper"
            self.table_issues.setItem(r_idx, 1, QTableWidgetItem(q_str))

            # Code
            self.table_issues.setItem(r_idx, 2, QTableWidgetItem(issue.code))

            # Description
            desc = issue.message
            if issue.details:
                desc += f" ({issue.details})"
            self.table_issues.setItem(r_idx, 3, QTableWidgetItem(desc))

        if not report.issues:
            self.table_issues.setRowCount(1)
            self.table_issues.setItem(0, 0, QTableWidgetItem("✓ PASS"))
            self.table_issues.setItem(0, 1, QTableWidgetItem("All"))
            self.table_issues.setItem(0, 2, QTableWidgetItem("CLEAN"))
            self.table_issues.setItem(0, 3, QTableWidgetItem("No defects or quality issues detected."))

        return report

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        self._on_jump_to_question()

    def _on_jump_to_question(self) -> None:
        row = self.table_issues.currentRow()
        if row < 0 or not self.audit_report or row >= len(self.audit_report.issues):
            return
        issue = self.audit_report.issues[row]
        if issue.question_id:
            self.navigate_to_question.emit(issue.question_id)
            self.accept()
