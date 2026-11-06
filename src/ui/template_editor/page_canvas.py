"""Interactive millimeter-scaled QGraphicsScene & QGraphicsView with Header/Footer Zone isolation."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from src.core.models.enums import CanvasElementType
from src.core.models.template_model import CanvasElement, Template
from src.ui.template_editor.canvas_items import CanvasGraphicsItem


class ZoneContainerItem(QGraphicsRectItem):
    """Container item representing an editable Header or Footer zone on the printable sheet."""

    def __init__(
        self,
        zone_name: str,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(0, 0, width_mm, height_mm, parent)
        self.zone_name = zone_name
        self.setPos(x_mm, y_mm)
        self.setPen(QPen(QColor("#2563EB"), 0.8, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(37, 99, 235, 12)))
        self.setZValue(1)

    def paint(
        self,
        painter: QPainter,
        option: object,
        widget: Optional[QWidget] = None,
    ) -> None:
        super().paint(painter, option, widget)
        # Draw small zone label in top-right corner
        painter.setPen(QColor("#2563EB"))
        font = QFont("Noto Sans", 7)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(2, 2, -4, -2),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            f"[{self.zone_name.upper()} ZONE]",
        )


class LockedBodyZoneItem(QGraphicsRectItem):
    """Strictly non-editable, locked visual zone reserved for dynamic question paper body content."""

    def __init__(
        self,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(0, 0, width_mm, height_mm, parent)
        self.setPos(x_mm, y_mm)
        self.setPen(QPen(QColor("#94A3B8"), 0.8, Qt.PenStyle.DotLine))
        self.setBrush(QBrush(QColor(241, 245, 249, 140)))
        self.setZValue(1)
        # Non-selectable, non-movable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setToolTip("🔒 Locked Body Area: Reserved for dynamic question paper content")

    def paint(
        self,
        painter: QPainter,
        option: object,
        widget: Optional[QWidget] = None,
    ) -> None:
        super().paint(painter, option, widget)
        rect = self.rect()
        painter.setPen(QColor("#64748B"))
        font = QFont("Noto Sans", 9)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter,
            "🔒 Reserved for Dynamic Question Paper Content\n(Body area cannot be edited in Template Designer)",
        )


class PageGraphicsScene(QGraphicsScene):
    """Millimeter-accurate QGraphicsScene rendering exact page geometry, zones, and canvas items."""

    element_selected = Signal(object)
    element_changed = Signal(object)

    def __init__(
        self,
        template: Template,
        is_first_page_mode: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.is_first_page_mode = is_first_page_mode

        self.header_zone_item: Optional[ZoneContainerItem] = None
        self.footer_zone_item: Optional[ZoneContainerItem] = None
        self.locked_body_item: Optional[LockedBodyZoneItem] = None
        self.canvas_items: List[CanvasGraphicsItem] = []

        self.rebuild_scene()

    def set_page_mode(self, is_first_page: bool) -> None:
        """Switch between First Page and Running Page elements."""
        self.is_first_page_mode = is_first_page
        self.rebuild_scene()

    def rebuild_scene(self) -> None:
        """Reconstruct page outline, margin guides, zone containers, and items from the template model."""
        self.clear()
        self.canvas_items.clear()

        setup = self.template.page_setup
        w_mm, h_mm = setup.effective_dimensions_mm
        m = setup.margins_mm
        printable_w = setup.printable_width_mm
        hdr_h = self.template.header_height_mm
        ftr_h = self.template.footer_height_mm

        # Set scene bounding rectangle (with generous margin padding around the sheet)
        padding = 20.0
        self.setSceneRect(-padding, -padding, w_mm + (2 * padding), h_mm + (2 * padding))

        # 1. Page Sheet (White background with drop shadow)
        shadow_rect = self.addRect(
            2.0,
            2.0,
            w_mm,
            h_mm,
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(15, 23, 42, 40)),
        )
        shadow_rect.setZValue(0)

        sheet_rect = self.addRect(
            0,
            0,
            w_mm,
            h_mm,
            QPen(QColor("#CBD5E1"), 0.8),
            QBrush(QColor("#FFFFFF")),
        )
        sheet_rect.setZValue(0.5)

        # 2. Printable Margin Guides (outer boundary of printable content)
        margin_guide = self.addRect(
            m.left,
            m.top,
            printable_w,
            h_mm - m.top - m.bottom,
            QPen(QColor("#CBD5E1"), 0.5, Qt.PenStyle.DashLine),
            QBrush(Qt.BrushStyle.NoBrush),
        )
        margin_guide.setZValue(0.8)

        # 3. Header Zone Item
        self.header_zone_item = ZoneContainerItem(
            zone_name="Header",
            x_mm=m.left,
            y_mm=m.top,
            width_mm=printable_w,
            height_mm=hdr_h,
        )
        self.addItem(self.header_zone_item)

        # 4. Locked Body Zone Item (Middle reserved space)
        body_y = m.top + hdr_h
        body_h = max(20.0, h_mm - m.top - m.bottom - hdr_h - ftr_h)
        self.locked_body_item = LockedBodyZoneItem(
            x_mm=m.left,
            y_mm=body_y,
            width_mm=printable_w,
            height_mm=body_h,
        )
        self.addItem(self.locked_body_item)

        # 5. Footer Zone Item
        ftr_y = h_mm - m.bottom - ftr_h
        self.footer_zone_item = ZoneContainerItem(
            zone_name="Footer",
            x_mm=m.left,
            y_mm=ftr_y,
            width_mm=printable_w,
            height_mm=ftr_h,
        )
        self.addItem(self.footer_zone_item)

        # 6. Populate Header & Footer Canvas Items
        hdr_elements = self.template.get_header_elements(is_first_page=self.is_first_page_mode)
        ftr_elements = self.template.get_footer_elements(is_first_page=self.is_first_page_mode)

        hdr_bounds = QRectF(0, 0, printable_w, hdr_h)
        for el in hdr_elements:
            c_item = CanvasGraphicsItem(el, zone_bounds_rect=hdr_bounds, parent=self.header_zone_item)
            c_item.item_selected.connect(self.element_selected.emit)
            c_item.item_geometry_changed.connect(self.element_changed.emit)
            c_item.setZValue(2)
            self.canvas_items.append(c_item)

        ftr_bounds = QRectF(0, 0, printable_w, ftr_h)
        for el in ftr_elements:
            c_item = CanvasGraphicsItem(el, zone_bounds_rect=ftr_bounds, parent=self.footer_zone_item)
            c_item.item_selected.connect(self.element_selected.emit)
            c_item.item_geometry_changed.connect(self.element_changed.emit)
            c_item.setZValue(2)
            self.canvas_items.append(c_item)

    def add_element_to_zone(self, element: CanvasElement, is_header: bool = True) -> CanvasGraphicsItem:
        """Append a new `CanvasElement` to the Header or Footer zone and add its visual item."""
        if self.is_first_page_mode and self.template.different_first_page:
            target_list = (
                self.template.first_page_header_elements
                if is_header
                else self.template.first_page_footer_elements
            )
        else:
            target_list = (
                self.template.running_header_elements
                if is_header
                else self.template.running_footer_elements
            )
        target_list.append(element)

        parent_zone = self.header_zone_item if is_header else self.footer_zone_item
        assert parent_zone is not None
        bounds = parent_zone.rect()

        c_item = CanvasGraphicsItem(element, zone_bounds_rect=bounds, parent=parent_zone)
        c_item.item_selected.connect(self.element_selected.emit)
        c_item.item_geometry_changed.connect(self.element_changed.emit)
        c_item.setZValue(2)
        self.canvas_items.append(c_item)

        self.clearSelection()
        c_item.setSelected(True)
        self.element_selected.emit(c_item)
        return c_item

    def remove_canvas_item(self, item: CanvasGraphicsItem) -> None:
        """Remove a canvas item from the scene and from the underlying template model."""
        el = item.element
        for el_list in (
            self.template.first_page_header_elements,
            self.template.running_header_elements,
            self.template.first_page_footer_elements,
            self.template.running_footer_elements,
        ):
            if el in el_list:
                el_list.remove(el)

        if item in self.canvas_items:
            self.canvas_items.remove(item)

        self.removeItem(item)
        self.element_selected.emit(None)


class PageGraphicsView(QGraphicsView):
    """Zoomable, pan-enabled interactive view of the template design sheet."""

    def __init__(self, scene: PageGraphicsScene, parent: Optional[QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setStyleSheet("background-color: #E2E8F0; border: none;")
        self._current_zoom = 1.0

    def zoom_in(self) -> None:
        self.set_zoom(self._current_zoom * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom(self._current_zoom / 1.2)

    def zoom_reset(self) -> None:
        self.set_zoom(1.0)

    def set_zoom(self, zoom: float) -> None:
        clamped = max(0.3, min(4.0, zoom))
        factor = clamped / self._current_zoom
        self._current_zoom = clamped
        self.scale(factor, factor)

    def fit_page(self) -> None:
        """Scale and center the sheet to fit entirely within the view."""
        self.resetTransform()
        self._current_zoom = 1.0
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom on Ctrl + Wheel or scroll normally."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
