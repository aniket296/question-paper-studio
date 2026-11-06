"""Interactive QGraphicsItem representations for Header & Footer Template Designer Canvas."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
)

from src.core.models.enums import CanvasElementType, TextAlignment
from src.core.models.template_model import CanvasElement

HANDLE_SIZE = 6.0  # Size in mm for resize handles


class CanvasGraphicsItem(QGraphicsObject):
    """Interactive visual representation of a `CanvasElement` in millimeters."""

    item_selected = Signal(object)
    item_geometry_changed = Signal(object)

    def __init__(
        self,
        element: CanvasElement,
        zone_bounds_rect: QRectF,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(parent)
        self.element = element
        self.zone_bounds = zone_bounds_rect

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        # Set initial position in mm relative to zone origin
        self.setPos(element.x_mm, element.y_mm)
        self._resizing = False
        self._active_handle: Optional[str] = None
        self._resize_start_pos = QPointF()
        self._resize_start_rect = QRectF()

    def boundingRect(self) -> QRectF:
        extra = max(2.0, self.element.line_thickness_pt * 0.352778)
        return QRectF(
            -extra,
            -extra,
            self.element.width_mm + (2 * extra),
            self.element.height_mm + (2 * extra),
        )

    def paint(
        self,
        painter: QPainter,
        option: object,
        widget: Optional[object] = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(0, 0, self.element.width_mm, self.element.height_mm)
        color = QColor(self.element.color_hex)

        if self.element.element_type == CanvasElementType.LINE:
            pen = QPen(color, max(0.5, self.element.line_thickness_pt * 0.352778))
            painter.setPen(pen)
            mid_y = rect.height() / 2.0
            painter.drawLine(QPointF(0, mid_y), QPointF(rect.width(), mid_y))

        elif self.element.element_type == CanvasElementType.BORDER:
            pen = QPen(color, max(0.5, self.element.line_thickness_pt * 0.352778))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        elif self.element.element_type == CanvasElementType.IMAGE:
            # Render image or placeholder box
            if self.element.content:
                pix = QPixmap(self.element.content)
                if not pix.isNull():
                    scaled = pix.scaled(
                        int(rect.width() * 4),
                        int(rect.height() * 4),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    painter.drawPixmap(rect.toRect(), scaled)
                else:
                    self._draw_image_placeholder(painter, rect, color)
            else:
                self._draw_image_placeholder(painter, rect, color)

        else:
            # TEXT or PAGE_NUMBER
            font = QFont(self.element.font_family, int(self.element.font_size_pt * 0.8))
            font.setBold(self.element.bold)
            font.setItalic(self.element.italic)
            font.setUnderline(self.element.underline)
            painter.setFont(font)
            painter.setPen(color)

            flags = Qt.AlignmentFlag.AlignVCenter
            if self.element.alignment == TextAlignment.CENTER:
                flags |= Qt.AlignmentFlag.AlignHCenter
            elif self.element.alignment == TextAlignment.RIGHT:
                flags |= Qt.AlignmentFlag.AlignRight
            else:
                flags |= Qt.AlignmentFlag.AlignLeft

            display_text = self.element.content or "Text Element"
            painter.drawText(rect, flags, display_text)

        # Highlight selection and draw resize handles
        if self.isSelected():
            sel_pen = QPen(QColor("#2563EB"), 1.0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            handle_pen = QPen(QColor("#1D4ED8"), 1.0)
            handle_brush = QBrush(QColor("#FFFFFF"))
            painter.setPen(handle_pen)
            painter.setBrush(handle_brush)
            for h_rect in self._get_handle_rects().values():
                painter.drawRect(h_rect)

    def _draw_image_placeholder(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        painter.setPen(QPen(QColor("#94A3B8"), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor("#F1F5F9")))
        painter.drawRect(rect)
        painter.setPen(QColor("#475569"))
        font = QFont("Noto Sans", 8)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "[ Logo / Image ]")

    def _get_handle_rects(self) -> dict[str, QRectF]:
        w = self.element.width_mm
        h = self.element.height_mm
        hs = HANDLE_SIZE
        half = hs / 2.0
        return {
            "top_left": QRectF(-half, -half, hs, hs),
            "top_right": QRectF(w - half, -half, hs, hs),
            "bottom_left": QRectF(-half, h - half, hs, hs),
            "bottom_right": QRectF(w - half, h - half, hs, hs),
            "right": QRectF(w - half, (h / 2.0) - half, hs, hs),
            "bottom": QRectF((w / 2.0) - half, h - half, hs, hs),
        }

    def _get_handle_at(self, point: QPointF) -> Optional[str]:
        for handle_name, h_rect in self._get_handle_rects().items():
            if h_rect.contains(point):
                return handle_name
        return None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isSelected():
            handle = self._get_handle_at(event.pos())
            if handle is not None:
                self._resizing = True
                self._active_handle = handle
                self._resize_start_pos = event.scenePos()
                self._resize_start_rect = QRectF(
                    self.element.x_mm,
                    self.element.y_mm,
                    self.element.width_mm,
                    self.element.height_mm,
                )
                event.accept()
                return

        super().mousePressEvent(event)
        self.item_selected.emit(self)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resizing and self._active_handle is not None:
            delta = event.scenePos() - self._resize_start_pos
            orig = self._resize_start_rect
            new_w = orig.width()
            new_h = orig.height()

            if "right" in self._active_handle:
                new_w = max(10.0, orig.width() + delta.x())
            if "bottom" in self._active_handle:
                new_h = max(4.0, orig.height() + delta.y())

            # Constrain to zone boundary
            new_w = min(new_w, self.zone_bounds.width() - self.element.x_mm)
            new_h = min(new_h, self.zone_bounds.height() - self.element.y_mm)

            self.prepareGeometryChange()
            self.element.width_mm = round(new_w, 1)
            self.element.height_mm = round(new_h, 1)
            self.update()
            self.item_geometry_changed.emit(self)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            self._resizing = False
            self._active_handle = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Enforce strict zone bounds so items cannot leave Header or Footer zone."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value if isinstance(value, QPointF) else self.pos()
            clamped_x = max(0.0, min(new_pos.x(), self.zone_bounds.width() - self.element.width_mm))
            clamped_y = max(0.0, min(new_pos.y(), self.zone_bounds.height() - self.element.height_mm))
            self.element.x_mm = round(clamped_x, 1)
            self.element.y_mm = round(clamped_y, 1)
            self.item_geometry_changed.emit(self)
            return QPointF(clamped_x, clamped_y)

        return super().itemChange(change, value)
