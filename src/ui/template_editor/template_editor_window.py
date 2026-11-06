"""WYSIWYG Header & Footer Template Designer Canvas Window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import CanvasElementType, TextAlignment
from src.core.models.template_model import CanvasElement, Template
from src.core.storage.template_store import TemplateStore
from src.ui.template_editor.canvas_items import CanvasGraphicsItem
from src.ui.template_editor.page_canvas import PageGraphicsScene, PageGraphicsView
from src.ui.template_editor.property_inspector import PropertyInspector


class TemplateEditorWindow(QWidget):
    """Complete visual designer shell for Header and Footer zones with zone-lock enforcement."""

    back_to_home_requested = Signal()
    template_saved = Signal(object)  # Emits saved Template

    def __init__(
        self,
        template_store: Optional[TemplateStore] = None,
        initial_template: Optional[Template] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.template_store = template_store or TemplateStore()
        self.template: Template = (
            initial_template.model_copy(deep=True)
            if initial_template is not None
            else Template(name="New Visual Template", is_builtin=False)
        )
        self.has_unsaved_changes: bool = False
        self._is_first_page_mode: bool = True

        self._build_ui()
        self.load_template(self.template)

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(10, 10, 10, 10)
        root_lay.setSpacing(8)

        # 1. Top Toolbar
        tb_frame = QFrame()
        tb_frame.setObjectName("CardFrame")
        tb_lay = QHBoxLayout(tb_frame)
        tb_lay.setContentsMargins(10, 8, 10, 8)
        tb_lay.setSpacing(10)

        self.btn_back = QPushButton("← Back to Home")
        self.btn_back.clicked.connect(self._on_back_clicked)
        tb_lay.addWidget(self.btn_back)

        name_lbl = QLabel("Template Name:")
        name_lbl.setStyleSheet("font-weight: 700;")
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Template Name...")
        self.edit_name.setMinimumWidth(180)
        self.edit_name.textChanged.connect(self._on_name_changed)
        tb_lay.addWidget(name_lbl)
        tb_lay.addWidget(self.edit_name)

        tb_lay.addSpacing(10)

        # Page Switcher (First Page vs Running Pages)
        self.page_switch_grp = QButtonGroup(self)
        self.btn_first_page = QPushButton("First Page Header/Footer")
        self.btn_first_page.setCheckable(True)
        self.btn_first_page.setChecked(True)
        self.btn_running_page = QPushButton("All Other Pages (Running)")
        self.btn_running_page.setCheckable(True)

        self.page_switch_grp.addButton(self.btn_first_page, 0)
        self.page_switch_grp.addButton(self.btn_running_page, 1)
        self.page_switch_grp.idClicked.connect(self._on_page_mode_switched)

        tb_lay.addWidget(self.btn_first_page)
        tb_lay.addWidget(self.btn_running_page)

        tb_lay.addSpacing(10)

        # Insertion Controls
        self.combo_zone_target = QComboBox()
        self.combo_zone_target.addItem("Target: Header", True)
        self.combo_zone_target.addItem("Target: Footer", False)
        tb_lay.addWidget(self.combo_zone_target)

        self.btn_add_text = QPushButton("+ Text")
        self.btn_add_text.clicked.connect(lambda: self.add_new_element(CanvasElementType.TEXT))
        self.btn_add_image = QPushButton("+ Logo/Image")
        self.btn_add_image.clicked.connect(lambda: self.add_new_element(CanvasElementType.IMAGE))
        self.btn_add_line = QPushButton("+ Line")
        self.btn_add_line.clicked.connect(lambda: self.add_new_element(CanvasElementType.LINE))
        self.btn_add_border = QPushButton("+ Border")
        self.btn_add_border.clicked.connect(lambda: self.add_new_element(CanvasElementType.BORDER))
        self.btn_add_pageno = QPushButton("+ Page No.")
        self.btn_add_pageno.clicked.connect(lambda: self.add_new_element(CanvasElementType.PAGE_NUMBER))

        tb_lay.addWidget(self.btn_add_text)
        tb_lay.addWidget(self.btn_add_image)
        tb_lay.addWidget(self.btn_add_line)
        tb_lay.addWidget(self.btn_add_border)
        tb_lay.addWidget(self.btn_add_pageno)

        tb_lay.addStretch(1)

        # Zoom Controls
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setToolTip("Zoom In")
        self.btn_zoom_in.clicked.connect(lambda: self.view.zoom_in())
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setToolTip("Zoom Out")
        self.btn_zoom_out.clicked.connect(lambda: self.view.zoom_out())
        self.btn_fit_page = QPushButton("Fit")
        self.btn_fit_page.setToolTip("Fit Sheet in View")
        self.btn_fit_page.clicked.connect(lambda: self.view.fit_page())

        tb_lay.addWidget(self.btn_zoom_in)
        tb_lay.addWidget(self.btn_zoom_out)
        tb_lay.addWidget(self.btn_fit_page)

        # Save Template Button
        self.btn_save_template = QPushButton("Save Template")
        self.btn_save_template.setObjectName("PrimaryButton")
        self.btn_save_template.clicked.connect(self.save_template)
        tb_lay.addWidget(self.btn_save_template)

        root_lay.addWidget(tb_frame)

        # 2. Main Work Area Splitter: Canvas View (Center) | Property Inspector (Right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.scene = PageGraphicsScene(self.template, is_first_page_mode=True)
        self.scene.element_selected.connect(self._on_scene_element_selected)
        self.scene.element_changed.connect(self._on_scene_element_changed)

        self.view = PageGraphicsView(self.scene)
        splitter.addWidget(self.view)

        self.inspector = PropertyInspector()
        self.inspector.page_setup_changed.connect(self._on_page_setup_modified)
        self.inspector.element_modified.connect(self._on_inspector_element_modified)
        self.inspector.delete_element_requested.connect(self._on_delete_element_requested)
        splitter.addWidget(self.inspector)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root_lay.addWidget(splitter, 1)

    def load_template(self, template: Template) -> None:
        """Load `template` into the editor canvas and property inspector."""
        self.template = template.model_copy(deep=True)
        self.edit_name.setText(self.template.name)
        self._is_first_page_mode = True
        self.btn_first_page.setChecked(True)
        self._update_page_switcher_visibility()

        self.scene.template = self.template
        self.scene.set_page_mode(is_first_page=True)
        self.inspector.load_template_properties(self.template)
        self.inspector.set_active_element(None)
        self.has_unsaved_changes = False

    def _update_page_switcher_visibility(self) -> None:
        has_diff = self.template.different_first_page
        self.btn_first_page.setEnabled(has_diff)
        self.btn_running_page.setEnabled(has_diff)
        if not has_diff:
            self._is_first_page_mode = False
            self.btn_running_page.setChecked(True)
            self.scene.set_page_mode(is_first_page=False)

    def _on_page_mode_switched(self, button_id: int) -> None:
        self._is_first_page_mode = button_id == 0
        self.scene.set_page_mode(is_first_page=self._is_first_page_mode)
        self.inspector.set_active_element(None)

    def _on_name_changed(self, text: str) -> None:
        self.template.name = text.strip() or "Untitled Template"
        self.has_unsaved_changes = True

    def _on_page_setup_modified(self) -> None:
        self.has_unsaved_changes = True
        self._update_page_switcher_visibility()
        self.scene.rebuild_scene()
        self.view.fit_page()

    def _on_scene_element_selected(self, item: Optional[CanvasGraphicsItem]) -> None:
        self.inspector.set_active_element(item)

    def _on_scene_element_changed(self, item: CanvasGraphicsItem) -> None:
        self.has_unsaved_changes = True
        self.inspector.sync_geometry_from_canvas(item)

    def _on_inspector_element_modified(self, item: CanvasGraphicsItem) -> None:
        self.has_unsaved_changes = True
        item.prepareGeometryChange()
        item.update()

    def _on_delete_element_requested(self, item: CanvasGraphicsItem) -> None:
        self.has_unsaved_changes = True
        self.scene.remove_canvas_item(item)

    def add_new_element(
        self,
        element_type: CanvasElementType,
        content: str = "",
        is_header: Optional[bool] = None,
    ) -> CanvasGraphicsItem:
        """Insert a new element into the Header or Footer zone."""
        target_is_header = (
            self.combo_zone_target.currentData() if is_header is None else is_header
        )
        self.has_unsaved_changes = True

        printable_w = self.template.page_setup.printable_width_mm

        if element_type == CanvasElementType.TEXT:
            el = CanvasElement(
                element_type=CanvasElementType.TEXT,
                x_mm=5.0,
                y_mm=4.0,
                width_mm=min(120.0, printable_w - 10.0),
                height_mm=8.0,
                font_size_pt=11.0,
                content=content or "New Text Box",
            )
        elif element_type == CanvasElementType.IMAGE:
            el = CanvasElement(
                element_type=CanvasElementType.IMAGE,
                x_mm=5.0,
                y_mm=2.0,
                width_mm=24.0,
                height_mm=24.0,
                content=content or "",
            )
        elif element_type == CanvasElementType.LINE:
            el = CanvasElement(
                element_type=CanvasElementType.LINE,
                x_mm=0.0,
                y_mm=10.0,
                width_mm=printable_w,
                height_mm=2.0,
                line_thickness_pt=1.5,
            )
        elif element_type == CanvasElementType.BORDER:
            el = CanvasElement(
                element_type=CanvasElementType.BORDER,
                x_mm=2.0,
                y_mm=2.0,
                width_mm=printable_w - 4.0,
                height_mm=20.0,
                line_thickness_pt=1.0,
            )
        else:
            # PAGE_NUMBER
            el = CanvasElement(
                element_type=CanvasElementType.PAGE_NUMBER,
                x_mm=printable_w - 65.0,
                y_mm=2.0,
                width_mm=60.0,
                height_mm=6.0,
                font_size_pt=9.5,
                alignment=TextAlignment.RIGHT,
                content=content or "Page {{page_number}} of {{total_pages}}",
            )

        c_item = self.scene.add_element_to_zone(el, is_header=target_is_header)
        return c_item

    def save_template(
        self,
        custom_path: Optional[Path | str] = None,
        confirm: bool = False,
    ) -> Path:
        """Persist template in `template_store` or `custom_path` and emit `template_saved`."""
        if not self.template.name.strip():
            self.template.name = "Custom Visual Template"

        saved_path = self.template_store.save_template(
            self.template,
            custom_path=custom_path,
            overwrite=True,
        )
        self.has_unsaved_changes = False
        self.template_saved.emit(self.template)

        if confirm:
            QMessageBox.information(
                self,
                "Template Saved",
                f"Template '{self.template.name}' saved successfully to:\n{saved_path}",
            )
        return saved_path

    def _on_back_clicked(self) -> None:
        if self.has_unsaved_changes:
            ans = QMessageBox.question(
                self,
                "Unsaved Template Changes",
                "You have unsaved changes in this template. Return to Home without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.back_to_home_requested.emit()
