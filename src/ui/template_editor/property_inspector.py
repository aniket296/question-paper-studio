"""Property Inspector panel for Page Setup, Header/Footer Zones, and Canvas Element Styling."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.models.enums import (
    CanvasElementType,
    Orientation,
    PageSize,
    TextAlignment,
)
from src.core.models.template_model import (
    SUPPORTED_PLACEHOLDERS,
    CanvasElement,
    PageSetup,
    Template,
)
from src.ui.template_editor.canvas_items import CanvasGraphicsItem


class PropertyInspector(QWidget):
    """Right-hand sidebar managing Page Setup, Zones, and selected CanvasElement styling."""

    page_setup_changed = Signal()
    element_modified = Signal(object)
    delete_element_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)

        self._current_template: Optional[Template] = None
        self._active_canvas_item: Optional[CanvasGraphicsItem] = None
        self._block_signals = False

        self._build_ui()

    @property
    def current_item(self) -> Optional[CanvasGraphicsItem]:
        """Return currently inspected canvas item, if any."""
        return self._active_canvas_item

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_widget = QWidget()
        self.content_lay = QVBoxLayout(content_widget)
        self.content_lay.setContentsMargins(12, 12, 12, 12)
        self.content_lay.setSpacing(14)

        # 1. Page Setup & Zones Group
        self.page_grp = QGroupBox("Page Setup & Boundaries")
        p_form = QFormLayout(self.page_grp)
        p_form.setSpacing(8)

        self.combo_page_size = QComboBox()
        for ps in (PageSize.A4, PageSize.A3, PageSize.LETTER, PageSize.CUSTOM):
            self.combo_page_size.addItem(ps.value, ps)
        self.combo_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        p_form.addRow("Page Size:", self.combo_page_size)

        self.combo_orientation = QComboBox()
        self.combo_orientation.addItem("Portrait", Orientation.PORTRAIT)
        self.combo_orientation.addItem("Landscape", Orientation.LANDSCAPE)
        self.combo_orientation.currentIndexChanged.connect(self._on_orientation_changed)
        p_form.addRow("Orientation:", self.combo_orientation)

        # Margins row
        m_row = QHBoxLayout()
        self.spin_top_margin = self._create_mm_spin(0.0, 60.0, 15.0)
        self.spin_bottom_margin = self._create_mm_spin(0.0, 60.0, 15.0)
        self.spin_left_margin = self._create_mm_spin(0.0, 60.0, 15.0)
        self.spin_right_margin = self._create_mm_spin(0.0, 60.0, 15.0)

        for sp in (
            self.spin_top_margin,
            self.spin_bottom_margin,
            self.spin_left_margin,
            self.spin_right_margin,
        ):
            sp.valueChanged.connect(self._on_margins_changed)

        m_form = QFormLayout()
        m_form.addRow("Top:", self.spin_top_margin)
        m_form.addRow("Bottom:", self.spin_bottom_margin)
        m_form.addRow("Left:", self.spin_left_margin)
        m_form.addRow("Right:", self.spin_right_margin)
        p_form.addRow("Margins (mm):", m_form)

        # Zone Heights
        self.spin_header_h = self._create_mm_spin(10.0, 120.0, 38.0)
        self.spin_header_h.valueChanged.connect(self._on_zones_changed)
        p_form.addRow("Header Height:", self.spin_header_h)

        self.spin_footer_h = self._create_mm_spin(8.0, 80.0, 14.0)
        self.spin_footer_h.valueChanged.connect(self._on_zones_changed)
        p_form.addRow("Footer Height:", self.spin_footer_h)

        self.chk_different_first = QCheckBox("Different First Page Header/Footer")
        self.chk_different_first.toggled.connect(self._on_different_first_toggled)
        p_form.addRow(self.chk_different_first)

        self.content_lay.addWidget(self.page_grp)

        # 2. Selected Element Inspector Group
        self.element_grp = QGroupBox("Selected Element Properties")
        e_form = QFormLayout(self.element_grp)
        e_form.setSpacing(8)

        # Position and Size
        geo_layout = QHBoxLayout()
        self.spin_x = self._create_mm_spin(0.0, 500.0, 0.0)
        self.spin_y = self._create_mm_spin(0.0, 500.0, 0.0)
        self.spin_w = self._create_mm_spin(5.0, 500.0, 50.0)
        self.spin_h = self._create_mm_spin(2.0, 500.0, 10.0)

        for sp in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            sp.valueChanged.connect(self._on_element_geometry_edited)

        g_form = QFormLayout()
        g_form.addRow("X (mm):", self.spin_x)
        g_form.addRow("Y (mm):", self.spin_y)
        g_form.addRow("Width:", self.spin_w)
        g_form.addRow("Height:", self.spin_h)
        e_form.addRow("Geometry:", g_form)

        # Content text / Dynamic variable inserter
        self.edit_content = QLineEdit()
        self.edit_content.textChanged.connect(self._on_element_content_edited)
        e_form.addRow("Content Text:", self.edit_content)

        # Dynamic Variable Chips dropdown
        chip_row = QHBoxLayout()
        self.combo_chips = QComboBox()
        self.combo_chips.addItem("Insert Dynamic Variable Chip...", "")
        for ph in SUPPORTED_PLACEHOLDERS:
            self.combo_chips.addItem(ph, ph)
        self.btn_insert_chip = QPushButton("Insert")
        self.btn_insert_chip.clicked.connect(self._on_insert_chip_clicked)
        chip_row.addWidget(self.combo_chips, 1)
        chip_row.addWidget(self.btn_insert_chip)
        e_form.addRow(chip_row)

        # Typography
        self.combo_font = QComboBox()
        fonts = ["Noto Sans", "Noto Sans Devanagari"] + QFontDatabase.families()[:25]
        self.combo_font.addItems(list(dict.fromkeys(fonts)))
        self.combo_font.currentTextChanged.connect(self._on_element_styling_edited)
        e_form.addRow("Font Family:", self.combo_font)

        self.spin_font_size = QDoubleSpinBox()
        self.spin_font_size.setRange(5.0, 72.0)
        self.spin_font_size.setValue(11.0)
        self.spin_font_size.setSingleStep(0.5)
        self.spin_font_size.valueChanged.connect(self._on_element_styling_edited)
        e_form.addRow("Font Size (pt):", self.spin_font_size)

        style_row = QHBoxLayout()
        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setStyleSheet("font-weight: bold;")
        self.btn_bold.toggled.connect(self._on_element_styling_edited)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style: italic;")
        self.btn_italic.toggled.connect(self._on_element_styling_edited)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setStyleSheet("text-decoration: underline;")
        self.btn_underline.toggled.connect(self._on_element_styling_edited)

        style_row.addWidget(self.btn_bold)
        style_row.addWidget(self.btn_italic)
        style_row.addWidget(self.btn_underline)
        e_form.addRow("Style:", style_row)

        align_row = QHBoxLayout()
        self.combo_alignment = QComboBox()
        self.combo_alignment.addItem("Left", TextAlignment.LEFT)
        self.combo_alignment.addItem("Center", TextAlignment.CENTER)
        self.combo_alignment.addItem("Right", TextAlignment.RIGHT)
        self.combo_alignment.currentIndexChanged.connect(self._on_element_styling_edited)
        align_row.addWidget(self.combo_alignment, 1)
        e_form.addRow("Alignment:", align_row)

        # Line thickness & Color
        self.spin_line_thick = QDoubleSpinBox()
        self.spin_line_thick.setRange(0.25, 20.0)
        self.spin_line_thick.setValue(1.0)
        self.spin_line_thick.setSingleStep(0.25)
        self.spin_line_thick.valueChanged.connect(self._on_element_styling_edited)
        e_form.addRow("Line Thickness:", self.spin_line_thick)

        color_row = QHBoxLayout()
        self.btn_color = QPushButton("Pick Color")
        self.btn_color.clicked.connect(self._on_pick_color)
        self.lbl_color_preview = QLabel("   ")
        self.lbl_color_preview.setStyleSheet("background-color: #000000; border: 1px solid #475569;")
        color_row.addWidget(self.btn_color)
        color_row.addWidget(self.lbl_color_preview, 1)
        e_form.addRow("Color:", color_row)

        # Image browse row (only active for IMAGE)
        self.image_row_widget = QWidget()
        img_row = QHBoxLayout(self.image_row_widget)
        img_row.setContentsMargins(0, 0, 0, 0)
        self.btn_browse_img = QPushButton("Browse Image...")
        self.btn_browse_img.clicked.connect(self._on_browse_image)
        img_row.addWidget(self.btn_browse_img)
        e_form.addRow(self.image_row_widget)

        # Delete element button
        self.btn_delete_element = QPushButton("Delete Element")
        self.btn_delete_element.setObjectName("DangerButton")
        self.btn_delete_element.clicked.connect(self._on_delete_element_clicked)
        e_form.addRow(self.btn_delete_element)

        self.content_lay.addWidget(self.element_grp)
        self.content_lay.addStretch(1)

        scroll.setWidget(content_widget)
        root_lay.addWidget(scroll)

        self.set_active_element(None)

    def _create_mm_spin(self, min_v: float, max_v: float, val: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setValue(val)
        sp.setSingleStep(1.0)
        sp.setDecimals(1)
        return sp

    def load_template_properties(self, template: Template) -> None:
        """Populate Page Setup inputs from `template`."""
        self._block_signals = True
        self._current_template = template
        setup = template.page_setup

        idx = self.combo_page_size.findData(setup.size)
        if idx >= 0:
            self.combo_page_size.setCurrentIndex(idx)

        idx_o = self.combo_orientation.findData(setup.orientation)
        if idx_o >= 0:
            self.combo_orientation.setCurrentIndex(idx_o)

        self.spin_top_margin.setValue(setup.margins_mm.top)
        self.spin_bottom_margin.setValue(setup.margins_mm.bottom)
        self.spin_left_margin.setValue(setup.margins_mm.left)
        self.spin_right_margin.setValue(setup.margins_mm.right)

        self.spin_header_h.setValue(template.header_height_mm)
        self.spin_footer_h.setValue(template.footer_height_mm)
        self.chk_different_first.setChecked(template.different_first_page)

        self._block_signals = False

    def set_active_element(self, item: Optional[CanvasGraphicsItem]) -> None:
        """Bind `item` to the element properties form or disable if None."""
        self._active_canvas_item = item
        if item is None:
            self.element_grp.setEnabled(False)
            return

        self._block_signals = True
        self.element_grp.setEnabled(True)
        el = item.element

        self.spin_x.setValue(el.x_mm)
        self.spin_y.setValue(el.y_mm)
        self.spin_w.setValue(el.width_mm)
        self.spin_h.setValue(el.height_mm)

        self.edit_content.setText(el.content)
        self.combo_font.setCurrentText(el.font_family)
        self.spin_font_size.setValue(el.font_size_pt)
        self.btn_bold.setChecked(el.bold)
        self.btn_italic.setChecked(el.italic)
        self.btn_underline.setChecked(el.underline)

        idx_a = self.combo_alignment.findData(el.alignment)
        if idx_a >= 0:
            self.combo_alignment.setCurrentIndex(idx_a)

        self.spin_line_thick.setValue(el.line_thickness_pt)
        self.lbl_color_preview.setStyleSheet(
            f"background-color: {el.color_hex}; border: 1px solid #475569;"
        )

        is_img = el.element_type == CanvasElementType.IMAGE
        self.image_row_widget.setVisible(is_img)

        self._block_signals = False

    def sync_geometry_from_canvas(self, item: CanvasGraphicsItem) -> None:
        """Called when item is moved or resized on canvas to update spinboxes."""
        if self._active_canvas_item == item and not self._block_signals:
            self._block_signals = True
            self.spin_x.setValue(item.element.x_mm)
            self.spin_y.setValue(item.element.y_mm)
            self.spin_w.setValue(item.element.width_mm)
            self.spin_h.setValue(item.element.height_mm)
            self._block_signals = False

    def _on_page_size_changed(self) -> None:
        if self._block_signals or not self._current_template:
            return
        ps = self.combo_page_size.currentData()
        self._current_template.page_setup.size = ps
        self.page_setup_changed.emit()

    def _on_orientation_changed(self) -> None:
        if self._block_signals or not self._current_template:
            return
        orient = self.combo_orientation.currentData()
        self._current_template.page_setup.orientation = orient
        self.page_setup_changed.emit()

    def _on_margins_changed(self) -> None:
        if self._block_signals or not self._current_template:
            return
        m = self._current_template.page_setup.margins_mm
        m.top = self.spin_top_margin.setValue and self.spin_top_margin.value()
        m.bottom = self.spin_bottom_margin.value()
        m.left = self.spin_left_margin.value()
        m.right = self.spin_right_margin.value()
        self.page_setup_changed.emit()

    def _on_zones_changed(self) -> None:
        if self._block_signals or not self._current_template:
            return
        self._current_template.header_height_mm = self.spin_header_h.value()
        self._current_template.footer_height_mm = self.spin_footer_h.value()
        self.page_setup_changed.emit()

    def _on_different_first_toggled(self, checked: bool) -> None:
        if self._block_signals or not self._current_template:
            return
        self._current_template.different_first_page = checked
        self.page_setup_changed.emit()

    def _on_element_geometry_edited(self) -> None:
        if self._block_signals or not self._active_canvas_item:
            return
        item = self._active_canvas_item
        item.element.x_mm = self.spin_x.value()
        item.element.y_mm = self.spin_y.value()
        item.element.width_mm = self.spin_w.value()
        item.element.height_mm = self.spin_h.value()
        item.setPos(item.element.x_mm, item.element.y_mm)
        item.prepareGeometryChange()
        item.update()
        self.element_modified.emit(item)

    def _on_element_content_edited(self, text: str) -> None:
        if self._block_signals or not self._active_canvas_item:
            return
        self._active_canvas_item.element.content = text
        self._active_canvas_item.update()
        self.element_modified.emit(self._active_canvas_item)

    def _on_insert_chip_clicked(self) -> None:
        chip = self.combo_chips.currentData()
        if chip and self._active_canvas_item:
            curr = self.edit_content.text()
            self.edit_content.setText(f"{curr} {chip}".strip())

    def _on_element_styling_edited(self) -> None:
        if self._block_signals or not self._active_canvas_item:
            return
        el = self._active_canvas_item.element
        el.font_family = self.combo_font.currentText()
        el.font_size_pt = self.spin_font_size.value()
        el.bold = self.btn_bold.isChecked()
        el.italic = self.btn_italic.isChecked()
        el.underline = self.btn_underline.isChecked()
        el.alignment = self.combo_alignment.currentData() or TextAlignment.LEFT
        el.line_thickness_pt = self.spin_line_thick.value()
        self._active_canvas_item.update()
        self.element_modified.emit(self._active_canvas_item)

    def _on_pick_color(self) -> None:
        if not self._active_canvas_item:
            return
        cur_color = QColor(self._active_canvas_item.element.color_hex)
        chosen = QColorDialog.getColor(cur_color, self, "Select Element Color")
        if chosen.isValid():
            hex_str = chosen.name().upper()
            self._active_canvas_item.element.color_hex = hex_str
            self.lbl_color_preview.setStyleSheet(
                f"background-color: {hex_str}; border: 1px solid #475569;"
            )
            self._active_canvas_item.update()
            self.element_modified.emit(self._active_canvas_item)

    def _on_browse_image(self) -> None:
        if not self._active_canvas_item:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Logo or Diagram Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.svg *.bmp);;All Files (*.*)",
        )
        if path:
            self._active_canvas_item.element.content = path
            self.edit_content.setText(path)
            self._active_canvas_item.update()
            self.element_modified.emit(self._active_canvas_item)

    def _on_delete_element_clicked(self) -> None:
        if self._active_canvas_item:
            self.delete_element_requested.emit(self._active_canvas_item)
