"""Real-Time Live Print Preview Pane for Question Paper Creation Workspace.

Features:
- Dual-mode renderer: interactive `QWebEngineView` with fallback to `QTextBrowser`
  (for headless CI / pytest / restricted environments).
- Live zoom controls: Zoom In, Zoom Out, 100% Reset, and Fit to Width.
- Debounced compilation (300ms default) to avoid lag during rapid typing in editors.
- Student View (standard exam sheet) vs Teacher Preview (answer key badges, rubrics).
- Instant recompile triggers and status feedback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models.project_model import ProjectState
from src.rendering.html_compiler import HTMLCompiler


class LivePreviewPane(QWidget):
    """Real-time HTML5 print preview pane with debounced compilation and zoom controls."""

    preview_updated = Signal(str)
    preview_rendered = Signal()

    def __init__(
        self,
        project: Optional[ProjectState] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project: Optional[ProjectState] = project
        self.teacher_preview_mode: bool = False
        self.zoom_factor: float = 1.0
        self._compiled_html: str = ""
        self._is_rendering: bool = False

        # Debounce timer for live background compilation
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._compile_and_render)

        self._build_ui()

        if self.project is not None:
            self.refresh_preview(immediate=True)

    def _is_headless_environment(self) -> bool:
        """Check whether we are running in headless pytest / offscreen mode."""
        return (
            os.environ.get("PYTEST_CURRENT_TEST") is not None
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Header Toolbar
        tb_frame = QFrame()
        tb_frame.setStyleSheet(
            "background-color: #F8FAFC; border-bottom: 1px solid #E2E8F0; padding: 4px;"
        )
        tb_lay = QHBoxLayout(tb_frame)
        tb_lay.setContentsMargins(8, 4, 8, 4)
        tb_lay.setSpacing(6)

        title_lbl = QLabel("👁 Live Print Preview")
        title_lbl.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 10pt;")
        tb_lay.addWidget(title_lbl)

        tb_lay.addSpacing(6)

        # Student vs Teacher Preview Mode Toggle
        self.btn_mode_toggle = QPushButton("👨‍🎓 Student View")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setChecked(False)
        self.btn_mode_toggle.setToolTip("Toggle between Student Exam View and Teacher Preview with Answer Keys")
        self.btn_mode_toggle.setStyleSheet("""
            QPushButton {
                background-color: #E2E8F0;
                color: #1E293B;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: 600;
                font-size: 9pt;
            }
            QPushButton:checked {
                background-color: #059669;
                color: #FFFFFF;
            }
        """)
        self.btn_mode_toggle.toggled.connect(self._on_mode_toggled)
        tb_lay.addWidget(self.btn_mode_toggle)

        tb_lay.addStretch(1)

        # Zoom Controls
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("−")
        self.btn_zoom_out.setToolTip("Zoom Out (10%)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        tb_lay.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("font-weight: 600; color: #475569; min-width: 40px; qproperty-alignment: AlignCenter;")
        tb_lay.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.setToolTip("Zoom In (10%)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        tb_lay.addWidget(self.btn_zoom_in)

        self.btn_zoom_reset = QToolButton()
        self.btn_zoom_reset.setText("1:1")
        self.btn_zoom_reset.setToolTip("Reset Zoom to 100%")
        self.btn_zoom_reset.clicked.connect(self.zoom_reset)
        tb_lay.addWidget(self.btn_zoom_reset)

        self.btn_zoom_fit = QToolButton()
        self.btn_zoom_fit.setText("⤢ Fit")
        self.btn_zoom_fit.setToolTip("Fit to Width")
        self.btn_zoom_fit.clicked.connect(self.zoom_fit_width)
        tb_lay.addWidget(self.btn_zoom_fit)

        tb_lay.addSpacing(6)

        # Refresh button
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("🔄")
        self.btn_refresh.setToolTip("Refresh Print Preview")
        self.btn_refresh.clicked.connect(lambda: self.refresh_preview(immediate=True))
        tb_lay.addWidget(self.btn_refresh)

        layout.addWidget(tb_frame)

        # 2. Main Viewer Area
        self._init_viewer_widget(layout)

        # 3. Bottom Preview Status Indicator
        self.status_bar = QFrame()
        self.status_bar.setStyleSheet("background-color: #F1F5F9; border-top: 1px solid #E2E8F0; padding: 2px 8px;")
        sb_lay = QHBoxLayout(self.status_bar)
        sb_lay.setContentsMargins(8, 2, 8, 2)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 8.5pt;")
        sb_lay.addWidget(self.lbl_status)

        sb_lay.addStretch(1)

        self.lbl_page_info = QLabel("A4 Portrait")
        self.lbl_page_info.setStyleSheet("color: #64748B; font-size: 8.5pt;")
        sb_lay.addWidget(self.lbl_page_info)

        layout.addWidget(self.status_bar)

    def _init_viewer_widget(self, parent_layout: QVBoxLayout) -> None:
        """Instantiate either `QWebEngineView` or `QTextBrowser` depending on environment."""
        if not self._is_headless_environment():
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView

                self.web_view = QWebEngineView(self)
                self.viewer_widget = self.web_view
                self._is_webengine = True
                parent_layout.addWidget(self.web_view, 1)
                return
            except Exception:
                pass

        # Fallback to QTextBrowser for offscreen/test runs or when WebEngine is unavailable
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setStyleSheet("background-color: #525659; border: none;")
        self.viewer_widget = self.text_browser
        self._is_webengine = False
        parent_layout.addWidget(self.text_browser, 1)

    # ========================================================================
    # Project & State Management
    # ========================================================================

    def set_project(self, project: Optional[ProjectState]) -> None:
        """Attach a new or modified `ProjectState` and schedule preview compilation."""
        self.project = project
        if project:
            setup = project.template_snapshot.page_setup
            self.lbl_page_info.setText(f"{setup.size.value} {setup.orientation.value}")
        self.refresh_preview(immediate=True)

    def set_teacher_preview_mode(self, enabled: bool) -> None:
        """Enable or disable teacher preview mode with answer key annotations."""
        if self.teacher_preview_mode != enabled:
            self.teacher_preview_mode = enabled
            self.btn_mode_toggle.setChecked(enabled)
            self._update_mode_label()
            self.refresh_preview(immediate=True)

    def _on_mode_toggled(self, checked: bool) -> None:
        self.teacher_preview_mode = checked
        self._update_mode_label()
        self.refresh_preview(immediate=True)

    def _update_mode_label(self) -> None:
        if self.teacher_preview_mode:
            self.btn_mode_toggle.setText("👨‍🏫 Teacher Preview")
        else:
            self.btn_mode_toggle.setText("👨‍🎓 Student View")

    def refresh_preview(self, immediate: bool = False) -> None:
        """Trigger compilation and re-rendering, either debounced or immediately."""
        if not self.project:
            self._set_viewer_html("<div style='padding:40px;text-align:center;color:#64748B;'>No question paper project loaded.</div>")
            return

        if immediate:
            self._debounce_timer.stop()
            self._compile_and_render()
        else:
            self.lbl_status.setText("Compiling preview...")
            self._debounce_timer.start()

    def _compile_and_render(self) -> None:
        """Compile the project AST into HTML5 and load it into the viewer widget."""
        if not self.project:
            return

        self._is_rendering = True
        self.lbl_status.setText("Rendering...")
        try:
            html_doc = HTMLCompiler.compile_project(
                self.project,
                teacher_preview_mode=self.teacher_preview_mode,
                preview_sheet_framing=True,
            )
            self._compiled_html = html_doc
            self._set_viewer_html(html_doc)
            self.lbl_status.setText(f"Preview updated ({'Teacher' if self.teacher_preview_mode else 'Student'} View)")
            self.preview_updated.emit(html_doc)
            self.preview_rendered.emit()
        except Exception as e:
            self.lbl_status.setText(f"Render Error: {e}")
        finally:
            self._is_rendering = False

    def _set_viewer_html(self, html_doc: str) -> None:
        """Load `html_doc` into active viewer widget."""
        if getattr(self, "_is_webengine", False):
            base_url = QUrl("file:///")
            self.web_view.setHtml(html_doc, base_url)
            self.web_view.setZoomFactor(self.zoom_factor)
        else:
            self.text_browser.setHtml(html_doc)

    def get_compiled_html(self) -> str:
        """Return the most recently compiled HTML document string."""
        return self._compiled_html

    # ========================================================================
    # Zoom Controls
    # ========================================================================

    def set_zoom_factor(self, factor: float) -> None:
        """Set zoom factor clamped between 0.4 (40%) and 3.0 (300%)."""
        clamped = max(0.4, min(3.0, factor))
        self.zoom_factor = round(clamped, 2)
        pct = int(self.zoom_factor * 100)
        self.lbl_zoom.setText(f"{pct}%")

        if getattr(self, "_is_webengine", False):
            self.web_view.setZoomFactor(self.zoom_factor)
        else:
            # Zoom for QTextBrowser via font point size adjustment
            font = self.text_browser.font()
            base_size = 10
            font.setPointSize(max(6, int(base_size * self.zoom_factor)))
            self.text_browser.setFont(font)

    def zoom_in(self) -> None:
        """Increase zoom by 10%."""
        self.set_zoom_factor(self.zoom_factor + 0.1)

    def zoom_out(self) -> None:
        """Decrease zoom by 10%."""
        self.set_zoom_factor(self.zoom_factor - 0.1)

    def zoom_reset(self) -> None:
        """Reset zoom to 100%."""
        self.set_zoom_factor(1.0)

    def zoom_fit_width(self) -> None:
        """Fit preview comfortably within width of the current pane."""
        # Standard A4 at 96 DPI is ~794px. Estimate ratio based on pane width:
        view_w = max(300, self.viewer_widget.width() - 40)
        target_zoom = view_w / 820.0
        self.set_zoom_factor(target_zoom)
