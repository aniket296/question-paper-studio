"""Unit and UI tests for Sub-phase 3.2: WYSIWYG Header & Footer Template Designer Canvas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem
from pytestqt.qtbot import QtBot

from src.core.models.enums import CanvasElementType, Orientation, PageSize, TextAlignment
from src.core.models.template_model import CanvasElement, Margins, PageSetup, Template
from src.core.storage.template_store import TemplateStore
from src.ui.main_window import MainWindow
from src.ui.template_editor.canvas_items import CanvasGraphicsItem
from src.ui.template_editor.page_canvas import PageGraphicsScene, PageGraphicsView
from src.ui.template_editor.property_inspector import PropertyInspector
from src.ui.template_editor.template_editor_window import TemplateEditorWindow


def test_page_canvas_geometry_and_locked_body_zone(qtbot: QtBot) -> None:
    """Verify PageGraphicsScene computes correct zone boundaries and enforces locked body zone."""
    setup = PageSetup(
        page_size=PageSize.A4,
        orientation=Orientation.PORTRAIT,
        margins_mm=Margins(top=10.0, bottom=10.0, left=15.0, right=15.0),
    )
    tmpl = Template(
        name="Geometry Test",
        page_setup=setup,
        header_height_mm=35.0,
        footer_height_mm=25.0,
    )
    scene = PageGraphicsScene(template=tmpl)
    view = PageGraphicsView(scene)
    qtbot.addWidget(view)
    view.show()

    # Verify sheet dimensions (A4: 210 x 297 mm in scene millimeter coordinates)
    w_mm, h_mm = setup.effective_dimensions_mm
    assert w_mm == 210.0
    assert h_mm == 297.0

    # Verify header, body, and footer zone positions in mm
    hdr_item = scene.header_zone_item
    assert hdr_item is not None
    assert hdr_item.rect().height() == 35.0
    assert hdr_item.rect().width() == setup.printable_width_mm
    assert hdr_item.pos().y() == 10.0  # margin top

    ftr_item = scene.footer_zone_item
    assert ftr_item is not None
    assert ftr_item.rect().height() == 25.0
    assert ftr_item.pos().y() == h_mm - 10.0 - 25.0

    body_item = scene.locked_body_item
    assert body_item is not None
    assert body_item.rect().height() > 0
    # Body starts right below header
    assert body_item.pos().y() == 10.0 + 35.0

    # Verify LockedBodyZoneItem displays locked body area tooltip
    assert "Locked" in body_item.toolTip()


def test_canvas_item_clamping_within_zone(qtbot: QtBot) -> None:
    """Verify CanvasGraphicsItem cannot cross zone boundaries or enter the locked middle body area."""
    setup = PageSetup(
        page_size=PageSize.A4,
        header_height_mm=40.0,
        footer_height_mm=25.0,
    )
    tmpl = Template(name="Clamping Test", page_setup=setup)
    scene = PageGraphicsScene(template=tmpl)
    el = CanvasElement(
        element_type=CanvasElementType.TEXT,
        x_mm=5.0,
        y_mm=5.0,
        width_mm=50.0,
        height_mm=15.0,
        content="Clamped School Title",
    )
    item = scene.add_element_to_zone(el, is_header=True)
    assert item is not None
    assert item.parentItem() == scene.header_zone_item

    # Attempt to move item far below header boundary (e.g. y = 500 mm, into locked body area)
    clamped_pos = item.itemChange(
        QGraphicsItem.GraphicsItemChange.ItemPositionChange,
        QPointF(10.0, 500.0),
    )
    # The clamped position's bottom cannot exceed header container height (40 mm)
    max_y = scene.header_zone_item.rect().height() - item.element.height_mm
    assert clamped_pos.y() <= max_y + 0.01

    # Attempt to move item above top boundary (e.g. y = -50 mm)
    clamped_top = item.itemChange(
        QGraphicsItem.GraphicsItemChange.ItemPositionChange,
        QPointF(10.0, -50.0),
    )
    assert clamped_top.y() >= 0.0


def test_template_editor_window_full_workflow(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify TemplateEditorWindow item creation, property inspection, page switching, and persistence."""
    store = TemplateStore(storage_dir=tmp_path / "templates")
    editor = TemplateEditorWindow(template_store=store)
    qtbot.addWidget(editor)
    editor.show()

    # 1. Add Text Element
    text_item = editor.add_new_element(CanvasElementType.TEXT, content="Delhi Public School")
    assert text_item is not None
    assert text_item in editor.scene.canvas_items

    # 2. Select item and verify PropertyInspector updates
    editor.scene.clearSelection()
    text_item.setSelected(True)
    assert editor.inspector.current_item == text_item
    assert "Delhi Public School" in editor.inspector.edit_content.text()

    # 3. Modify element properties via PropertyInspector
    editor.inspector.spin_font_size.setValue(18.0)
    assert text_item.element.font_size_pt == 18.0
    editor.inspector.btn_bold.click()
    assert text_item.element.bold is True

    # 4. Insert dynamic variable chip
    idx = editor.inspector.combo_chips.findData("{{exam_name}}")
    assert idx >= 0
    editor.inspector.combo_chips.setCurrentIndex(idx)
    editor.inspector.btn_insert_chip.click()
    assert "{{exam_name}}" in editor.inspector.edit_content.text()

    # 5. Add Line, Border, and Page Number items
    line_item = editor.add_new_element(CanvasElementType.LINE)
    border_item = editor.add_new_element(CanvasElementType.BORDER)
    pg_item = editor.add_new_element(CanvasElementType.PAGE_NUMBER)
    assert line_item is not None
    assert border_item is not None
    assert pg_item is not None

    # 6. Test different first page toggle and page switcher
    assert editor._is_first_page_mode is False  # By default, different_first_page is False -> running header
    editor.inspector.chk_different_first.setChecked(True)
    assert editor.template.different_first_page is True
    assert editor.btn_first_page.isEnabled() is True
    assert editor.btn_running_page.isEnabled() is True

    # Switch to first page
    editor.btn_first_page.click()
    assert editor._is_first_page_mode is True
    first_page_text = editor.add_new_element(CanvasElementType.TEXT, content="First Page Header")
    assert first_page_text is not None

    # Switch to running pages
    editor.btn_running_page.click()
    assert editor._is_first_page_mode is False
    running_text = editor.add_new_element(CanvasElementType.TEXT, content="Running Header")
    assert running_text is not None

    # 7. Modify PageSetup via PropertyInspector (header height)
    editor.inspector.spin_header_h.setValue(45.0)
    assert editor.template.header_height_mm == 45.0
    assert editor.scene.header_zone_item.rect().height() == 45.0

    # 8. Save template and verify file on disk
    editor.edit_name.setText("Greenwood High Annual Exam")
    saved_path = editor.save_template(confirm=False)
    assert saved_path.exists()
    assert ".json" in saved_path.name
    assert editor.has_unsaved_changes is False

    # Reload saved template from store and verify properties
    loaded = store.get_template(editor.template.template_id)
    assert loaded is not None
    assert loaded.name == "Greenwood High Annual Exam"
    assert loaded.header_height_mm == 45.0


def test_main_window_template_editor_routing(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify MainWindow integrates TemplateEditorWindow seamlessly and updates on save."""
    win = MainWindow(workspace_dir=tmp_path / "ws")
    qtbot.addWidget(win)
    win.show()

    home = win.home_screen
    # Select built-in template and edit it
    home.select_template_by_id("builtin-standard-school-a4")
    tmpl = home.template_store.get_template("builtin-standard-school-a4")
    assert tmpl is not None

    win.open_edit_template_editor(tmpl)
    assert win.stack.currentIndex() == MainWindow.ROUTE_TEMPLATE_EDITOR
    assert isinstance(win.template_editor_view, TemplateEditorWindow)
    assert win.template_editor_view.template.template_id != tmpl.template_id  # Duplicated for edit

    # Make change and save
    win.template_editor_view.edit_name.setText("Custom School Standard")
    win.template_editor_view.save_template(confirm=False)

    # Verify home screen refreshed and template appears in templates
    win.navigate_home(force=True)
    assert win.stack.currentIndex() == MainWindow.ROUTE_HOME
    all_tmpls = win.home_screen.template_store.list_templates()
    assert any(t.name == "Custom School Standard" for t in all_tmpls)
