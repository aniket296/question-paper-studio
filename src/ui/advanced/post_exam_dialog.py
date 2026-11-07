"""Post-Exam Candidate Marks Entry, Item Analysis & Psychometric Diagnostic Dialog.

Calculates:
1. Item Difficulty Index (P-value: proportion of candidates earning marks).
2. Item Discrimination Index (D-value: top 27% vs bottom 27% performance delta).
3. Class summary statistics (Mean, Median, Standard Deviation, Pass Rate).
4. Exportable CSV and HTML Diagnostic Performance Reports.
"""

from __future__ import annotations

import csv
import html
import math
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.engine.marks_engine import MarksEngine
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode


class PostExamDialog(QDialog):
    """Dialog for candidate marks entry, psychometric item analysis, and report generation."""

    def __init__(
        self,
        project: ProjectState,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: ProjectState = project
        self.questions: List[QuestionNode] = [
            q for q in self.project.all_questions_dfs()
            if not q.children and (q.marks or 0.0) > 0
        ]

        self.setWindowTitle("📊 Post-Exam Diagnostic & Candidate Marks Entry")
        self.setMinimumWidth(920)
        self.setMinimumHeight(640)

        self._build_ui()
        self._populate_initial_candidates(count=15)
        self.compute_psychometrics()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setSpacing(12)

        # 1. Header Banner
        lbl_title = QLabel("📊 Post-Exam Diagnostics & Item Analysis")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0F172A;")
        root_lay.addWidget(lbl_title)

        lbl_sub = QLabel("Record student scores, evaluate Question Difficulty (P-value) & Discrimination (D-value), and export diagnostic reports.")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 9.5pt;")
        root_lay.addWidget(lbl_sub)

        # 2. Candidate controls toolbar
        bar = QHBoxLayout()
        self.btn_add_student = QPushButton("+ Add Candidate")
        self.btn_add_student.clicked.connect(self._add_candidate_row)
        self.btn_simulate = QPushButton("🎲 Simulate Class Scores (25 Candidates)")
        self.btn_simulate.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: 600;")
        self.btn_simulate.clicked.connect(lambda: self._populate_initial_candidates(count=25, randomize=True))
        self.btn_recalculate = QPushButton("⚡ Recalculate Psychometrics")
        self.btn_recalculate.clicked.connect(self.compute_psychometrics)

        bar.addWidget(self.btn_add_student)
        bar.addWidget(self.btn_simulate)
        bar.addWidget(self.btn_recalculate)
        bar.addStretch(1)
        root_lay.addLayout(bar)

        # 3. Main Multi-Tab Viewer
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-weight: 600; padding: 6px 14px; }")

        # Tab 1: Marks Entry Grid
        self.tab_grid = QWidget()
        g_lay = QVBoxLayout(self.tab_grid)
        g_lay.setContentsMargins(8, 8, 8, 8)
        self.table_marks = QTableWidget(0, 0)
        self.table_marks.setAlternatingRowColors(True)
        self.table_marks.cellChanged.connect(self._on_marks_cell_changed)
        g_lay.addWidget(self.table_marks)
        self.tabs.addTab(self.tab_grid, "📝 Candidate Scores Grid")

        # Tab 2: Psychometric Item Analysis Table
        self.tab_metrics = QWidget()
        m_lay = QVBoxLayout(self.tab_metrics)
        m_lay.setContentsMargins(8, 8, 8, 8)
        self.table_metrics = QTableWidget(0, 6)
        self.table_metrics.setHorizontalHeaderLabels([
            "Question", "Max Marks", "Mean Score", "Difficulty (P)", "Discrimination (D)", "Evaluation Rating"
        ])
        self.table_metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_metrics.setAlternatingRowColors(True)
        m_lay.addWidget(self.table_metrics)
        self.tabs.addTab(self.tab_metrics, "📈 Item Difficulty & Discrimination (P & D)")

        # Tab 3: Class Summary Statistics
        self.tab_summary = QWidget()
        s_lay = QVBoxLayout(self.tab_summary)
        s_lay.setContentsMargins(12, 12, 12, 12)
        s_lay.setSpacing(8)

        self.lbl_stats_mean = QLabel("Mean Exam Score: --")
        self.lbl_stats_mean.setStyleSheet("font-size: 11pt; font-weight: 700; color: #2563EB;")
        self.lbl_stats_sd = QLabel("Standard Deviation: --")
        self.lbl_stats_sd.setStyleSheet("font-size: 11pt; color: #475569;")
        self.lbl_stats_pass = QLabel("Pass Rate (>= 40%): --")
        self.lbl_stats_pass.setStyleSheet("font-size: 11pt; font-weight: 600; color: #16A34A;")

        s_lay.addWidget(self.lbl_stats_mean)
        s_lay.addWidget(self.lbl_stats_sd)
        s_lay.addWidget(self.lbl_stats_pass)
        s_lay.addStretch(1)
        self.tabs.addTab(self.tab_summary, "📋 Class Summary Statistics")

        root_lay.addWidget(self.tabs, 1)

        # 4. Action and Export Buttons
        btn_box = QHBoxLayout()
        self.btn_export_csv = QPushButton("📤 Export CSV Report")
        self.btn_export_csv.clicked.connect(self.export_csv)
        self.btn_export_html = QPushButton("📤 Export HTML Diagnostic")
        self.btn_export_html.clicked.connect(self.export_html)
        btn_box.addWidget(self.btn_export_csv)
        btn_box.addWidget(self.btn_export_html)
        btn_box.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        root_lay.addLayout(btn_box)

    def _setup_grid_headers(self) -> None:
        headers = ["Candidate Name"]
        for q in self.questions:
            num = q.resolved_number or "Q"
            m = q.marks or 0.0
            headers.append(f"{num} ({m:g}M)")
        headers.extend(["Total", "Percentage"])

        self.table_marks.setColumnCount(len(headers))
        self.table_marks.setHorizontalHeaderLabels(headers)

    def _populate_initial_candidates(self, count: int = 15, randomize: bool = False) -> None:
        self._block_calc = True
        try:
            self._setup_grid_headers()
            self.table_marks.setRowCount(count)

            rng = random.Random(42)

            for r in range(count):
                name_item = QTableWidgetItem(f"Student {r + 1:02d}")
                self.table_marks.setItem(r, 0, name_item)

                for c_idx, q in enumerate(self.questions, start=1):
                    max_m = q.marks or 2.0
                    if randomize:
                        ratio = rng.triangular(0.2, 1.0, 0.7)
                        val = round(max_m * ratio, 1)
                    else:
                        val = round(max_m * 0.75, 1)

                    cell = QTableWidgetItem(f"{val:g}")
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table_marks.setItem(r, c_idx, cell)

                # Total and Percentage slots
                self.table_marks.setItem(r, len(self.questions) + 1, QTableWidgetItem("0"))
                self.table_marks.setItem(r, len(self.questions) + 2, QTableWidgetItem("0%"))
        finally:
            self._block_calc = False

        self.compute_psychometrics()

    def _add_candidate_row(self) -> None:
        self._block_calc = True
        try:
            row = self.table_marks.rowCount()
            self.table_marks.insertRow(row)
            self.table_marks.setItem(row, 0, QTableWidgetItem(f"Student {row + 1:02d}"))
            for c in range(1, len(self.questions) + 1):
                cell = QTableWidgetItem("0")
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_marks.setItem(row, c, cell)
            self.table_marks.setItem(row, len(self.questions) + 1, QTableWidgetItem("0"))
            self.table_marks.setItem(row, len(self.questions) + 2, QTableWidgetItem("0%"))
        finally:
            self._block_calc = False
        self.compute_psychometrics()

    def _on_marks_cell_changed(self, row: int, col: int) -> None:
        if getattr(self, "_block_calc", False):
            return
        self.compute_psychometrics()

    def compute_psychometrics(self) -> None:
        """Calculate total scores, Item Difficulty Index (P), and Discrimination (D)."""
        num_candidates = self.table_marks.rowCount()
        if num_candidates == 0 or len(self.questions) == 0:
            return

        total_paper_marks = sum(q.marks or 0.0 for q in self.questions)
        candidate_totals: List[Tuple[int, float]] = []  # (row_index, total_score)

        # 1. Compute candidate totals
        self._block_calc = True
        try:
            for r in range(num_candidates):
                tot = 0.0
                for c_idx, q in enumerate(self.questions, start=1):
                    item = self.table_marks.item(r, c_idx)
                    if item:
                        try:
                            tot += float(item.text())
                        except ValueError:
                            pass
                candidate_totals.append((r, tot))

                tot_col = len(self.questions) + 1
                pct_col = len(self.questions) + 2
                self.table_marks.setItem(r, tot_col, QTableWidgetItem(f"{tot:g}"))
                pct_val = (tot / total_paper_marks * 100.0) if total_paper_marks > 0 else 0.0
                self.table_marks.setItem(r, pct_col, QTableWidgetItem(f"{pct_val:.1f}%"))
        finally:
            self._block_calc = False

        # Sort candidates by total score
        sorted_candidates = sorted(candidate_totals, key=lambda x: x[1], reverse=True)
        scores_only = [x[1] for x in candidate_totals]

        # Class stats
        mean_score = sum(scores_only) / num_candidates
        variance = sum((s - mean_score) ** 2 for s in scores_only) / num_candidates
        std_dev = math.sqrt(variance)
        pass_count = sum(1 for s in scores_only if (s / total_paper_marks >= 0.4)) if total_paper_marks > 0 else 0
        pass_rate = (pass_count / num_candidates) * 100.0

        self.lbl_stats_mean.setText(f"Mean Score: {mean_score:.2f} / {total_paper_marks:g} M ({mean_score / total_paper_marks * 100:.1f}%)" if total_paper_marks > 0 else "0 M")
        self.lbl_stats_sd.setText(f"Standard Deviation: {std_dev:.2f}")
        self.lbl_stats_pass.setText(f"Pass Rate (>=40%): {pass_rate:.1f}% ({pass_count}/{num_candidates} students)")

        # 2. Item-level psychometrics (P-value & D-value)
        # Upper 27% and Lower 27% groups for discrimination
        group_size = max(1, int(round(num_candidates * 0.27)))
        top_rows = [x[0] for x in sorted_candidates[:group_size]]
        bottom_rows = [x[0] for x in sorted_candidates[-group_size:]]

        self.table_metrics.setRowCount(len(self.questions))
        self.item_metrics: List[Dict[str, float | str]] = []

        for q_idx, q in enumerate(self.questions):
            col = q_idx + 1
            max_m = q.marks or 1.0

            # Mean item score across all candidates
            item_scores = []
            for r in range(num_candidates):
                item = self.table_marks.item(r, col)
                if item:
                    try:
                        item_scores.append(float(item.text()))
                    except ValueError:
                        item_scores.append(0.0)
                else:
                    item_scores.append(0.0)

            mean_item = sum(item_scores) / num_candidates
            p_val = mean_item / max_m if max_m > 0 else 0.0

            # Top and bottom group means
            top_mean = sum(item_scores[r] for r in top_rows) / len(top_rows)
            bot_mean = sum(item_scores[r] for r in bottom_rows) / len(bottom_rows)
            d_val = (top_mean - bot_mean) / max_m if max_m > 0 else 0.0

            # Rating
            if d_val >= 0.40:
                rating = "Excellent Item"
            elif d_val >= 0.30:
                rating = "Good Item"
            elif d_val >= 0.20:
                rating = "Marginal — Needs Review"
            else:
                rating = "Poor Discrimination"

            self.table_metrics.setItem(q_idx, 0, QTableWidgetItem(q.resolved_number or f"Q{q_idx + 1}"))
            self.table_metrics.setItem(q_idx, 1, QTableWidgetItem(f"{max_m:g} M"))
            self.table_metrics.setItem(q_idx, 2, QTableWidgetItem(f"{mean_item:.2f}"))
            self.table_metrics.setItem(q_idx, 3, QTableWidgetItem(f"{p_val:.2f}"))
            self.table_metrics.setItem(q_idx, 4, QTableWidgetItem(f"{d_val:.2f}"))

            r_item = QTableWidgetItem(rating)
            if d_val >= 0.30:
                r_item.setForeground(Qt.GlobalColor.darkGreen)
            elif d_val >= 0.20:
                r_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                r_item.setForeground(Qt.GlobalColor.darkRed)
            self.table_metrics.setItem(q_idx, 5, r_item)

            self.item_metrics.append({
                "number": q.resolved_number or f"Q{q_idx + 1}",
                "max_marks": max_m,
                "mean": mean_item,
                "p_val": p_val,
                "d_val": d_val,
                "rating": rating,
            })

    def export_csv(self, dest_path: Optional[Path] = None) -> Optional[Path]:
        """Export scores and item analysis metrics to a CSV spreadsheet."""
        if dest_path is None:
            chosen, _ = QFileDialog.getSaveFileName(self, "Export Diagnostic CSV", "exam_item_analysis.csv", "CSV Files (*.csv)")
            if not chosen:
                return None
            dest = Path(chosen)
        else:
            dest = Path(dest_path)

        with dest.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 1. Candidate scores
            headers = [self.table_marks.horizontalHeaderItem(c).text() for c in range(self.table_marks.columnCount())]
            writer.writerow(["CANDIDATE SCORES"])
            writer.writerow(headers)
            for r in range(self.table_marks.rowCount()):
                row_vals = [self.table_marks.item(r, c).text() if self.table_marks.item(r, c) else "" for c in range(self.table_marks.columnCount())]
                writer.writerow(row_vals)

            writer.writerow([])
            writer.writerow(["ITEM PSYCHOMETRICS (DIFFICULTY P & DISCRIMINATION D)"])
            writer.writerow(["Question", "Max Marks", "Mean Score", "Difficulty P", "Discrimination D", "Rating"])
            for m in getattr(self, "item_metrics", []):
                writer.writerow([m["number"], m["max_marks"], f"{m['mean']:.2f}", f"{m['p_val']:.2f}", f"{m['d_val']:.2f}", m["rating"]])

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            QMessageBox.information(self, "Export Complete", f"Saved diagnostic CSV report to:\n{dest.name}")
        return dest

    def export_html(self, dest_path: Optional[Path] = None) -> Optional[Path]:
        """Export rich HTML5 diagnostic performance dashboard."""
        if dest_path is None:
            chosen, _ = QFileDialog.getSaveFileName(self, "Export Diagnostic HTML", "exam_diagnostic_report.html", "HTML Files (*.html)")
            if not chosen:
                return None
            dest = Path(chosen)
        else:
            dest = Path(dest_path)

        rows_html = "".join(
            f"<tr><td><b>{m['number']}</b></td><td>{m['max_marks']:g} M</td><td>{m['mean']:.2f}</td><td>{m['p_val']:.2f}</td><td>{m['d_val']:.2f}</td><td>{m['rating']}</td></tr>"
            for m in getattr(self, "item_metrics", [])
        )

        doc_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Post-Exam Psychometric Diagnostic Report — {html.escape(self.project.title)}</title>
    <style>
        body {{ font-family: 'Noto Sans', 'Segoe UI', Arial, sans-serif; padding: 24px; color: #0F172A; }}
        h1 {{ color: #1E293B; margin-bottom: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 10pt; }}
        th, td {{ border: 1px solid #CBD5E1; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #F1F5F9; font-weight: 700; }}
        tr:nth-child(even) {{ background-color: #F8FAFC; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; font-weight: 600; }}
    </style>
</head>
<body>
    <h1>Post-Exam Psychometric Diagnostic Report</h1>
    <p><b>Examination:</b> {html.escape(self.project.title)} | <b>Candidates Evaluated:</b> {self.table_marks.rowCount()}</p>
    <p>{html.escape(self.lbl_stats_mean.text())} | {html.escape(self.lbl_stats_sd.text())} | {html.escape(self.lbl_stats_pass.text())}</p>
    <table>
        <thead>
            <tr>
                <th>Question</th>
                <th>Max Marks</th>
                <th>Mean Score</th>
                <th>Difficulty (P)</th>
                <th>Discrimination (D)</th>
                <th>Item Evaluation</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""
        dest.write_text(doc_html, encoding="utf-8")
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            QMessageBox.information(self, "Export Complete", f"Saved diagnostic HTML dashboard to:\n{dest.name}")
        return dest
