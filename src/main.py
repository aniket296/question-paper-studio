"""Application Entrypoint for Question Paper Studio desktop application.

Provides:
- Application startup with high-DPI scaling and font registration.
- Theme application and application icon configuration.
- Routing to `MainWindow` with optional `.qpf` file loading.
- `--self-test` CLI flag for headless automated smoke testing and installer validation.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

# Ensure project root is in sys.path when invoked directly as python src/main.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import MCQData, MCQOption, QuestionNode
from src.core.models.template_model import Template
from src.core.storage.qpf_archive import QPFArchive
from src.core.storage.template_store import TemplateStore
from src.rendering.docx_exporter import DOCXExporter
from src.rendering.html_compiler import HTMLCompiler
from src.rendering.pdf_exporter import PDFExporter
from src.ui.main_window import MainWindow
from src.ui.theme import ICONS_DIR, ThemeManager


def run_self_test() -> int:
    """Execute headless environment, engine, and UI smoke tests for CI and installer verification."""
    print("=" * 60)
    print("Question Paper Studio — Headless Self-Test")
    print("=" * 60)

    # 1. Initialize QApplication
    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication(["--platform", "offscreen"])

    # 2. Font registration
    fonts = ThemeManager.register_bundled_fonts()
    print(f"[1/6] Bundled Fonts: Registered {len(fonts)} family/families ({', '.join(fonts) if fonts else 'system fallback'}).")

    # 3. Template store
    t_store = TemplateStore()
    templates = t_store.list_templates()
    assert len(templates) > 0, "TemplateStore has no built-in templates."
    tmpl = templates[0]
    print(f"[2/6] Template Store: Found {len(templates)} built-in templates (using '{tmpl.name}').")

    # 4. Project state AST construction
    project = ProjectState.create_from_template(tmpl, title="Self-Test Exam Paper")
    q1 = QuestionNode(
        question_type=QuestionType.MCQ,
        prompt_html="<p>What is the SI unit of electric current? $\\oint \\vec{B} \\cdot d\\vec{l} = \\mu_0 I$</p>",
        marks=2.0,
        type_data=MCQData(
            options=[
                MCQOption(label="A", text_html="Ampere", is_correct=True),
                MCQOption(label="B", text_html="Volt", is_correct=False),
                MCQOption(label="C", text_html="Ohm", is_correct=False),
                MCQOption(label="D", text_html="Watt", is_correct=False),
            ],
            allow_multiple_correct=False,
        ),
    )
    project.sections[0].questions.append(q1)
    print(f"[3/6] AST Model: Successfully constructed ProjectState with {len(project.all_questions_dfs())} question(s).")

    # 5. HTML and DOCX compiler tests
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir)

        # HTML
        html_out = HTMLCompiler.compile_project(project)
        assert "<html" in html_out and "Ampere" in html_out
        print("[4/6] HTML Compiler: Successfully compiled print-ready HTML5 document.")

        # DOCX
        docx_file = tmp_path / "self_test.docx"
        DOCXExporter.export_project_to_docx(project, docx_file)
        assert docx_file.exists() and docx_file.stat().st_size > 0
        print(f"[5/6] DOCX Exporter: Generated valid DOCX ({docx_file.stat().st_size} bytes).")

        # UI Window
        main_win = MainWindow(workspace_dir=tmp_path / "workspace")
        assert main_win.stack.count() == 3
        print("[6/6] GUI Shell: MainWindow and 3-Pane Workspace instantiated cleanly.")
        main_win.question_bank.close()

    print("=" * 60)
    print("All Self-Test checks passed successfully! (Exit 0)")
    print("=" * 60)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for Question Paper Studio."""
    parser = argparse.ArgumentParser(
        prog="question-paper-studio",
        description="Question Paper Studio — Industry-grade Question Paper Generator",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-diagnostic checks headlessly and exit 0 if healthy.",
    )
    parser.add_argument(
        "--dark",
        action="store_true",
        help="Launch application with dark mode theme enabled.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Optional path to a .qpf question paper archive to open on launch.",
    )

    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    # Launch desktop application GUI
    app = QApplication(sys.argv)
    app.setApplicationName("Question Paper Studio")
    app.setOrganizationName("QuestionPaperStudio")

    # Apply application icon if present
    icon_ico = ICONS_DIR / "app_icon.ico"
    icon_png = ICONS_DIR / "app_icon.png"
    if icon_ico.exists():
        app.setWindowIcon(QIcon(str(icon_ico)))
    elif icon_png.exists():
        app.setWindowIcon(QIcon(str(icon_png)))

    # Apply typography & theme stylesheet
    ThemeManager.apply_theme(app, dark_mode=args.dark)

    window = MainWindow()

    # Open project file if specified
    if args.file:
        file_path = Path(args.file)
        if file_path.exists() and file_path.suffix.lower() == ".qpf":
            try:
                res = QPFArchive.load_qpf(file_path)
                window.open_existing_paper_workspace(res.project, qpf_path=file_path)
            except Exception as e:
                print(f"Failed to load file '{file_path}': {e}", file=sys.stderr)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
