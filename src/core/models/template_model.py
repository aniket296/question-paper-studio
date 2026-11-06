"""Template domain models: PageSetup, Margins, CanvasElement, and Template."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.models.enums import (
    CanvasElementType,
    Orientation,
    PageSize,
    TextAlignment,
)

SUPPORTED_PLACEHOLDERS: Tuple[str, ...] = (
    "{{exam_name}}",
    "{{subject_name}}",
    "{{subject_code}}",
    "{{class_semester}}",
    "{{exam_date}}",
    "{{duration}}",
    "{{max_marks}}",
    "{{set_identifier}}",
    "{{page_number}}",
    "{{total_pages}}",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Margins(BaseModel):
    """Page margins in millimeters."""

    model_config = ConfigDict(validate_assignment=True)

    top: float = Field(default=15.0, ge=0.0, le=100.0)
    bottom: float = Field(default=15.0, ge=0.0, le=100.0)
    left: float = Field(default=15.0, ge=0.0, le=100.0)
    right: float = Field(default=15.0, ge=0.0, le=100.0)


class PageSetup(BaseModel):
    """Printable page geometry and margin setup."""

    model_config = ConfigDict(validate_assignment=True)

    size: PageSize = Field(default=PageSize.A4)
    orientation: Orientation = Field(default=Orientation.PORTRAIT)
    custom_width_mm: Optional[float] = Field(default=None, gt=50.0, le=1000.0)
    custom_height_mm: Optional[float] = Field(default=None, gt=50.0, le=1000.0)
    margins_mm: Margins = Field(default_factory=Margins)

    @model_validator(mode="after")
    def _validate_custom_dimensions_and_margins(self) -> "PageSetup":
        if self.size == PageSize.CUSTOM:
            if self.custom_width_mm is None:
                object.__setattr__(self, "custom_width_mm", 210.0)
            if self.custom_height_mm is None:
                object.__setattr__(self, "custom_height_mm", 297.0)

        w, h = self.effective_dimensions_mm
        if self.margins_mm.left + self.margins_mm.right >= w - 30.0:
            raise ValueError("Horizontal margins exceed printable page width.")
        if self.margins_mm.top + self.margins_mm.bottom >= h - 40.0:
            raise ValueError("Vertical margins exceed printable page height.")
        return self

    @property
    def effective_dimensions_mm(self) -> Tuple[float, float]:
        """Return effective (width_mm, height_mm) accounting for page size and orientation."""
        if self.size == PageSize.CUSTOM:
            base_w = self.custom_width_mm or 210.0
            base_h = self.custom_height_mm or 297.0
        else:
            base_w, base_h = self.size.default_dimensions_mm

        if self.orientation == Orientation.LANDSCAPE:
            return (max(base_w, base_h), min(base_w, base_h))
        return (min(base_w, base_h), max(base_w, base_h))

    @property
    def printable_width_mm(self) -> float:
        """Width between left and right margins in millimeters."""
        w, _ = self.effective_dimensions_mm
        return w - self.margins_mm.left - self.margins_mm.right

    @property
    def printable_height_mm(self) -> float:
        """Height between top and bottom margins in millimeters."""
        _, h = self.effective_dimensions_mm
        return h - self.margins_mm.top - self.margins_mm.bottom


class CanvasElement(BaseModel):
    """A visual element placed inside the Header or Footer zone of a Template."""

    model_config = ConfigDict(validate_assignment=True)

    element_id: str = Field(default_factory=lambda: str(uuid4()))
    element_type: CanvasElementType = Field(default=CanvasElementType.TEXT)

    # Geometry in millimeters relative to the enclosing Header or Footer zone origin
    x_mm: float = Field(default=0.0, ge=0.0)
    y_mm: float = Field(default=0.0, ge=0.0)
    width_mm: float = Field(default=50.0, gt=0.0)
    height_mm: float = Field(default=8.0, gt=0.0)

    # Typography and visual styling
    font_family: str = Field(default="Noto Sans")
    font_size_pt: float = Field(default=11.0, gt=4.0, le=72.0)
    bold: bool = Field(default=False)
    italic: bool = Field(default=False)
    underline: bool = Field(default=False)
    alignment: TextAlignment = Field(default=TextAlignment.LEFT)
    color_hex: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    line_thickness_pt: float = Field(default=1.0, ge=0.1, le=20.0)

    # Content: text/placeholder string, relative asset path, or page number format
    content: str = Field(default="")

    def render_placeholders(self, context: Dict[str, str]) -> str:
        """Substitute runtime `{{placeholder}}` tokens in `content` using `context`."""
        result = self.content
        for key, val in context.items():
            token = key if key.startswith("{{") else f"{{{{{key}}}}}"
            result = result.replace(token, str(val))
        return result


class Template(BaseModel):
    """Header & Footer visual template strictly decoupled from question paper content."""

    model_config = ConfigDict(validate_assignment=True)

    template_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(default="Standard School Exam Template", min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    is_builtin: bool = Field(default=False)

    page_setup: PageSetup = Field(default_factory=PageSetup)
    header_height_mm: float = Field(default=35.0, ge=5.0, le=120.0)
    footer_height_mm: float = Field(default=15.0, ge=5.0, le=80.0)
    different_first_page: bool = Field(default=False)

    first_page_header_elements: List[CanvasElement] = Field(default_factory=list)
    running_header_elements: List[CanvasElement] = Field(default_factory=list)
    first_page_footer_elements: List[CanvasElement] = Field(default_factory=list)
    running_footer_elements: List[CanvasElement] = Field(default_factory=list)

    # Optional visual backdrop path when imported from a static PDF/DOCX reference
    imported_backdrop_asset: Optional[str] = Field(default=None)
    source_format: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _validate_zone_heights_and_elements(self) -> "Template":
        printable_h = self.page_setup.printable_height_mm
        if self.header_height_mm + self.footer_height_mm >= printable_h - 40.0:
            raise ValueError(
                "Combined header and footer heights leave insufficient middle body zone for questions."
            )

        printable_w = self.page_setup.printable_width_mm
        for zone_elements, max_h, zone_name in (
            (self.first_page_header_elements, self.header_height_mm, "first_page_header"),
            (self.running_header_elements, self.header_height_mm, "running_header"),
            (self.first_page_footer_elements, self.footer_height_mm, "first_page_footer"),
            (self.running_footer_elements, self.footer_height_mm, "running_footer"),
        ):
            for el in zone_elements:
                if el.x_mm > printable_w:
                    raise ValueError(
                        f"Element '{el.element_id}' in {zone_name} exceeds printable width ({printable_w} mm)."
                    )
                if el.y_mm > max_h:
                    raise ValueError(
                        f"Element '{el.element_id}' in {zone_name} exceeds zone height ({max_h} mm)."
                    )
        return self

    @property
    def body_zone_height_mm(self) -> float:
        """Height of the locked middle region reserved for dynamic question paper content."""
        return self.page_setup.printable_height_mm - self.header_height_mm - self.footer_height_mm

    def get_header_elements(self, is_first_page: bool = True) -> List[CanvasElement]:
        """Return active header elements for the first page or subsequent running pages."""
        if is_first_page and self.different_first_page:
            return self.first_page_header_elements
        return self.running_header_elements

    def get_footer_elements(self, is_first_page: bool = True) -> List[CanvasElement]:
        """Return active footer elements for the first page or subsequent running pages."""
        if is_first_page and self.different_first_page:
            return self.first_page_footer_elements
        return self.running_footer_elements

    def create_snapshot(self) -> "Template":
        """Return a deep, independent copy of this template for embedding inside a ProjectState."""
        return self.model_copy(deep=True)

    def duplicate(self, new_name: Optional[str] = None) -> "Template":
        """Create a new editable user template cloned from this template with new UUIDs."""
        cloned = self.model_copy(deep=True)
        cloned.template_id = str(uuid4())
        cloned.name = new_name or f"{self.name} (Copy)"
        cloned.is_builtin = False
        now = _utc_now()
        cloned.created_at = now
        cloned.updated_at = now
        for el_list in (
            cloned.first_page_header_elements,
            cloned.running_header_elements,
            cloned.first_page_footer_elements,
            cloned.running_footer_elements,
        ):
            for el in el_list:
                el.element_id = str(uuid4())
        return cloned
