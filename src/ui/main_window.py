"""Root Application Window (`MainWindow`) and Screen Router for Question Paper Studio.

Manages:
- Central `QStackedWidget` routing between:
  0: `HomeScreen` (Launcher, Template Management, Recent `.qpf` Projects)
  1: `TemplateEditorWindow` / view (Header/Footer visual designer)
  2: `WorkspaceScreen` / view (3-Pane Question Paper Creation Workspace)
- Unsaved-change warning prompts before closing or returning to Home.
- Crash recovery detection (`AutosaveManager`) on startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.models.project_model import ProjectState
from src.core.models.template_model import Template
from src.core.storage.autosave_manager import AutosaveManager, RecoveryCandidate
from src.core.storage.sqlite_bank import SQLiteQuestionBank
from src.core.storage.template_store import TemplateStore
from src.ui.home.home_screen import HomeScreen
from src.ui.template_editor.template_editor_window import TemplateEditorWindow

DEFAULT_WORKSPACE_DIR = Path.home() / ".question_paper_studio"


class _PlaceholderRouteView(QWidget):
    """Lightweight route container used until specialized sub-phase views are attached."""

    back_to_home_requested = Signal()

    def __init__(self, route_title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.back_btn = QPushButton("← Back to Home")
        self.back_btn.clicked.connect(self.back_to_home_requested.emit)
        self.title_label = QLabel(route_title)
        self.title_label.setStyleSheet("font-size: 14pt; font-weight: 700;")
        top.addWidget(self.back_btn)
        top.addWidget(self.title_label, 1)
        lay.addLayout(top)
        lay.addStretch(1)


class MainWindow(QMainWindow):
    """Root application controller and navigation router."""

    ROUTE_HOME = 0
    ROUTE_TEMPLATE_EDITOR = 1
    ROUTE_WORKSPACE = 2

    def __init__(
        self,
        workspace_dir: Optional[Path | str] = None,
        template_store: Optional[TemplateStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Question Paper Studio")
        self.resize(1280, 820)

        self.workspace_dir = Path(workspace_dir) if workspace_dir else DEFAULT_WORKSPACE_DIR
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.autosave_manager = AutosaveManager(self.workspace_dir)
        self.template_store = template_store or TemplateStore(self.autosave_manager.templates_dir)
        self.question_bank = SQLiteQuestionBank(self.workspace_dir / "workspace.db")

        self.active_project: Optional[ProjectState] = None
        self.active_project_path: Optional[Path] = None
        self.active_template_editing: Optional[Template] = None
        self.has_unsaved_changes: bool = False

        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        # Route 0: Home Screen
        self.home_screen = HomeScreen(
            template_store=self.template_store,
            projects_dir=self.autosave_manager.projects_dir,
            parent=self,
        )
        self.home_screen.create_paper_requested.connect(self.open_new_paper_workspace)
        self.home_screen.open_project_requested.connect(self.open_existing_paper_workspace)
        self.home_screen.create_template_requested.connect(self.open_new_template_editor)
        self.home_screen.edit_template_requested.connect(self.open_edit_template_editor)

        # Route 1: Template Editor
        self.template_editor_view = TemplateEditorWindow(
            template_store=self.template_store,
            parent=self,
        )
        self.template_editor_view.back_to_home_requested.connect(self.navigate_home)
        self.template_editor_view.template_saved.connect(self._on_template_saved)

        # Route 2: Paper Workspace slot
        self.workspace_view: QWidget = _PlaceholderRouteView("Question Paper Workspace", self)
        if isinstance(self.workspace_view, _PlaceholderRouteView):
            self.workspace_view.back_to_home_requested.connect(self.navigate_home)

        self.stack.addWidget(self.home_screen)           # Index 0
        self.stack.addWidget(self.template_editor_view)  # Index 1
        self.stack.addWidget(self.workspace_view)        # Index 2

        self.statusBar().showMessage("Ready — Select a template to create a question paper.")

    def _on_template_saved(self, template: Template) -> None:
        """Handle template saved in visual editor."""
        self.home_screen.refresh_templates()
        self.statusBar().showMessage(f"Template '{template.name}' saved successfully.")

    def set_template_editor_widget(self, widget: QWidget) -> None:
        """Replace Route 1 with the full WYSIWYG `TemplateEditorWindow` widget."""
        old = self.stack.widget(self.ROUTE_TEMPLATE_EDITOR)
        self.stack.removeWidget(old)
        old.deleteLater()
        self.template_editor_view = widget
        self.stack.insertWidget(self.ROUTE_TEMPLATE_EDITOR, widget)

    def set_workspace_widget(self, widget: QWidget) -> None:
        """Replace Route 2 with the full 3-Pane `WorkspaceScreen` widget."""
        old = self.stack.widget(self.ROUTE_WORKSPACE)
        self.stack.removeWidget(old)
        old.deleteLater()
        self.workspace_view = widget
        self.stack.insertWidget(self.ROUTE_WORKSPACE, widget)

    # ========================================================================
    # Navigation & Routing
    # ========================================================================

    def navigate_home(self, force: bool = False) -> bool:
        """Return to the Home Screen, prompting if there are unsaved workspace changes."""
        if not force and self.has_unsaved_changes:
            ans = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Return to Home Screen without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        self.has_unsaved_changes = False
        self.home_screen.refresh_templates()
        self.home_screen.refresh_recent_projects()
        self.stack.setCurrentIndex(self.ROUTE_HOME)
        self.statusBar().showMessage("Home — Ready")
        return True

    def open_new_paper_workspace(self, template: Template, title: str = "Untitled Question Paper") -> ProjectState:
        """Initialize a new `ProjectState` from `template` and route to the Question Paper Workspace."""
        project = ProjectState.create_from_template(template, title=title)
        self.active_project = project
        self.active_project_path = None
        self.has_unsaved_changes = False
        if hasattr(self.workspace_view, "load_project"):
            self.workspace_view.load_project(project)  # type: ignore[attr-defined]
        elif isinstance(self.workspace_view, _PlaceholderRouteView):
            self.workspace_view.title_label.setText(f"Workspace — {project.title} [{template.name}]")

        self.stack.setCurrentIndex(self.ROUTE_WORKSPACE)
        self.statusBar().showMessage(f"Editing Question Paper: {project.title} (Template: {template.name})")
        return project

    def open_existing_paper_workspace(
        self,
        project: ProjectState,
        qpf_path: Optional[Path] = None,
    ) -> ProjectState:
        """Load an existing `ProjectState` and route to the Question Paper Workspace."""
        self.active_project = project
        self.active_project_path = qpf_path
        self.has_unsaved_changes = False
        if hasattr(self.workspace_view, "load_project"):
            self.workspace_view.load_project(project, qpf_path=qpf_path)  # type: ignore[attr-defined]
        elif isinstance(self.workspace_view, _PlaceholderRouteView):
            self.workspace_view.title_label.setText(f"Workspace — {project.title}")

        self.stack.setCurrentIndex(self.ROUTE_WORKSPACE)
        self.statusBar().showMessage(f"Opened Question Paper: {project.title}")
        return project

    def open_new_template_editor(self) -> Template:
        """Create a fresh blank `Template` and route to the Template Editor."""
        new_tmpl = Template(name="New Custom Template", is_builtin=False)
        return self.open_edit_template_editor(new_tmpl)

    def open_edit_template_editor(self, template: Template) -> Template:
        """Route to the Template Editor loaded with `template` (duplicating if built-in)."""
        editable = template.duplicate() if template.is_builtin else template.model_copy(deep=True)
        self.active_template_editing = editable
        if hasattr(self.template_editor_view, "load_template"):
            self.template_editor_view.load_template(editable)  # type: ignore[attr-defined]
        elif isinstance(self.template_editor_view, _PlaceholderRouteView):
            self.template_editor_view.title_label.setText(f"Template Designer — {editable.name}")

        self.stack.setCurrentIndex(self.ROUTE_TEMPLATE_EDITOR)
        self.statusBar().showMessage(f"Designing Template: {editable.name}")
        return editable

    # ========================================================================
    # Crash Recovery & Window Lifecycle
    # ========================================================================

    def check_and_prompt_crash_recovery(self, auto_accept: Optional[bool] = None) -> Optional[ProjectState]:
        """Check for unrecovered autosave snapshots on startup and optionally restore them."""
        candidates = self.autosave_manager.list_unrecovered_snapshots()
        if not candidates:
            return None

        latest: RecoveryCandidate = candidates[-1]
        if auto_accept is None:
            ans = QMessageBox.question(
                self,
                "Recover Unsaved Question Paper",
                f"An unsaved question paper '{latest.title}' (saved at {latest.saved_at}) was found.\n\n"
                "Would you like to recover it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            should_recover = ans == QMessageBox.StandardButton.Yes
        else:
            should_recover = auto_accept

        if should_recover:
            recovered = self.autosave_manager.recover_project(latest)
            self.open_existing_paper_workspace(recovered)
            return recovered

        self.autosave_manager.mark_clean_close(latest.project_id)
        return None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Prompt before closing if unsaved changes exist, and close the SQLite connection cleanly."""
        if self.has_unsaved_changes:
            ans = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes in your current work. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        if self.active_project is not None:
            self.autosave_manager.mark_clean_close(self.active_project.project_id)
        self.question_bank.close()
        event.accept()
