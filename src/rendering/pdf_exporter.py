"""Vector PDF Exporter and Direct System Printer for Question Paper Studio.

Primary pipeline:
- Uses `QWebEnginePage.printToPdf()` with exact `QPageLayout` (millimeter page size,
  orientation, and margins) for pixel-identical fidelity with the live preview pane.
- Automatically falls back to Qt's `QTextDocument` + `QPdfWriter` vector PDF renderer
  when running inside restricted sandboxes where Chromium subprocess spawning is blocked.
- Supports direct system printing via `QPrintDialog` and `QPrinter`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEventLoop, QMarginsF, QSizeF, QTimer, QUrl
from PySide6.QtGui import (
    QPageLayout,
    QPageSize,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QApplication, QWidget

from src.core.models.enums import Orientation, PageSize
from src.core.models.project_model import ProjectState
from src.core.models.template_model import Template
from src.rendering.html_compiler import HTMLCompiler
from src.rendering.supplementary_builder import SupplementaryBuilder


def _ensure_qapp() -> QApplication:
    """Return existing QApplication instance or create a headless-capable instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def build_qpage_layout(template: Template) -> QPageLayout:
    """Construct a millimeter-accurate `QPageLayout` from `template.page_setup`."""
    setup = template.page_setup
    if setup.size == PageSize.A4:
        qsize = QPageSize(QPageSize.PageSizeId.A4)
    elif setup.size == PageSize.A3:
        qsize = QPageSize(QPageSize.PageSizeId.A3)
    elif setup.size == PageSize.LETTER:
        qsize = QPageSize(QPageSize.PageSizeId.Letter)
    else:
        w_mm = setup.custom_width_mm or 210.0
        h_mm = setup.custom_height_mm or 297.0
        qsize = QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter)

    orient = (
        QPageLayout.Orientation.Landscape
        if setup.orientation == Orientation.LANDSCAPE
        else QPageLayout.Orientation.Portrait
    )
    m = setup.margins_mm
    margins = QMarginsF(m.left, m.top, m.right, m.bottom)
    return QPageLayout(qsize, orient, margins, QPageLayout.Unit.Millimeter)


class PDFExporter:
    """Compiles HTML5 documents and `ProjectState` ASTs into print-ready vector PDF files."""

    @staticmethod
    def _should_use_webengine() -> bool:
        """Return True only when running in an interactive desktop GUI session outside pytest/headless CI."""
        if os.environ.get("QPS_FORCE_WEBENGINE_PDF") == "1":
            return True
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return False
        return True

    @staticmethod
    def render_html_to_pdf_bytes(
        html_content: str,
        template: Optional[Template] = None,
        base_dir: Optional[Path] = None,
        timeout_ms: int = 8000,
    ) -> bytes:
        """Compile `html_content` into vector PDF bytes using `QWebEnginePage.printToPdf` (with `QPdfWriter` fallback)."""
        _ensure_qapp()
        tmpl = template or Template()
        page_layout = build_qpage_layout(tmpl)

        if PDFExporter._should_use_webengine():
            pdf_bytes = PDFExporter._try_webengine_pdf_bytes(
                html_content=html_content,
                page_layout=page_layout,
                base_dir=base_dir,
                timeout_ms=timeout_ms,
            )
            if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                return pdf_bytes

        return PDFExporter._render_qpdfwriter_bytes(
            html_content=html_content,
            page_layout=page_layout,
        )

    @staticmethod
    def _try_webengine_pdf_bytes(
        html_content: str,
        page_layout: QPageLayout,
        base_dir: Optional[Path],
        timeout_ms: int,
    ) -> bytes:
        """Attempt rendering via `QWebEnginePage.printToPdf`."""
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = QWebEnginePage()
            loop = QEventLoop()
            result_holder: dict[str, bytes] = {"data": b""}

            def _on_pdf_ready(data: bytes) -> None:
                result_holder["data"] = bytes(data)
                if loop.isRunning():
                    loop.quit()

            def _on_load_finished(ok: bool) -> None:
                if not ok:
                    if loop.isRunning():
                        loop.quit()
                    return
                page.printToPdf(_on_pdf_ready, page_layout)

            page.loadFinished.connect(_on_load_finished)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(timeout_ms)

            base_url = (
                QUrl.fromLocalFile(str(base_dir.resolve()) + "/")
                if base_dir is not None
                else QUrl("file:///")
            )
            page.setHtml(html_content, base_url)
            loop.exec()
            page.deleteLater()
            return result_holder["data"]
        except Exception:
            return b""

    @staticmethod
    def _render_qpdfwriter_bytes(
        html_content: str,
        page_layout: QPageLayout,
    ) -> bytes:
        """Render vector PDF bytes using Qt's native `QPdfWriter` and `QTextDocument`."""
        from PySide6.QtCore import QBuffer, QIODevice

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)

        writer = QPdfWriter(buf)
        writer.setPageLayout(page_layout)
        writer.setResolution(300)

        doc = QTextDocument()
        doc.setHtml(html_content)
        doc.print_(writer)

        buf.close()
        return bytes(buf.data())

    @staticmethod
    def export_project_to_pdf(
        project: ProjectState,
        output_path: Path | str,
        teacher_preview_mode: bool = False,
        overwrite: bool = True,
        base_asset_dir: Optional[Path] = None,
        dynamic_seed: int = 101,
    ) -> Path:
        """Compile `project` into a vector PDF file at `output_path`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"PDF file '{dest}' already exists.")

        dest.parent.mkdir(parents=True, exist_ok=True)
        html_doc = HTMLCompiler.compile_project(
            project,
            teacher_preview_mode=teacher_preview_mode,
            preview_sheet_framing=False,
            base_asset_dir=base_asset_dir,
            dynamic_seed=dynamic_seed,
        )
        pdf_bytes = PDFExporter.render_html_to_pdf_bytes(
            html_content=html_doc,
            template=project.template_snapshot,
            base_dir=base_asset_dir,
        )
        dest.write_bytes(pdf_bytes)
        return dest

    @staticmethod
    def export_answer_key_pdf(
        project: ProjectState,
        output_path: Path | str,
        overwrite: bool = True,
        dynamic_seed: int = 101,
    ) -> Path:
        """Export a separate Answer Key PDF for `project`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Answer Key PDF '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_doc = SupplementaryBuilder.compile_answer_key_html(project, dynamic_seed=dynamic_seed)
        pdf_bytes = PDFExporter.render_html_to_pdf_bytes(html_doc, template=project.template_snapshot)
        dest.write_bytes(pdf_bytes)
        return dest

    @staticmethod
    def export_marking_scheme_pdf(
        project: ProjectState,
        output_path: Path | str,
        overwrite: bool = True,
        dynamic_seed: int = 101,
    ) -> Path:
        """Export a separate Marking Scheme / Rubric PDF for `project`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Marking Scheme PDF '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_doc = SupplementaryBuilder.compile_marking_scheme_html(project, dynamic_seed=dynamic_seed)
        pdf_bytes = PDFExporter.render_html_to_pdf_bytes(html_doc, template=project.template_snapshot)
        dest.write_bytes(pdf_bytes)
        return dest

    @staticmethod
    def export_candidate_sheet_pdf(
        project: ProjectState,
        output_path: Path | str,
        overwrite: bool = True,
    ) -> Path:
        """Export a separate Candidate Response / OMR Sheet PDF for `project`."""
        dest = Path(output_path)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Candidate Sheet PDF '{dest}' already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_doc = SupplementaryBuilder.compile_candidate_omr_sheet_html(project)
        pdf_bytes = PDFExporter.render_html_to_pdf_bytes(html_doc, template=project.template_snapshot)
        dest.write_bytes(pdf_bytes)
        return dest

    @staticmethod
    def print_project_Interactive(
        project: ProjectState,
        parent_widget: Optional[QWidget] = None,
    ) -> bool:
        """Open the native system `QPrintDialog` and print `project` if accepted by the user."""
        _ensure_qapp()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(build_qpage_layout(project.template_snapshot))

        dialog = QPrintDialog(printer, parent_widget)
        dialog.setWindowTitle(f"Print — {project.title}")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

        html_doc = HTMLCompiler.compile_project(project, teacher_preview_mode=False)
        doc = QTextDocument()
        doc.setHtml(html_doc)
        doc.print_(printer)
        return True
