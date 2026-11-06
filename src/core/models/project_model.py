"""Root ProjectState, ExamMetadata, and LayoutSettings models for `.qpf` projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.models.blueprint_model import ExamBlueprint
from src.core.models.enums import (
    BilingualLayout,
    CandidateFieldType,
    MarksPosition,
    SecondaryLanguage,
)
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import Section
from src.core.models.template_model import Template


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExamMetadata(BaseModel):
    """Optional examination header metadata and instructions."""

    model_config = ConfigDict(validate_assignment=True)

    exam_name: str = Field(default="")
    subject_name: str = Field(default="")
    subject_code: str = Field(default="")
    class_semester: str = Field(default="")
    exam_date: str = Field(default="")
    duration_minutes: Optional[int] = Field(default=None, ge=1)
    duration_display: str = Field(default="")
    max_marks: Optional[float] = Field(default=None, ge=0.0)
    set_identifier: str = Field(default="")

    general_instructions: str = Field(default="")
    candidate_fields: List[CandidateFieldType] = Field(default_factory=list)
    watermark_text: Optional[str] = Field(default=None)

    def to_placeholder_context(
        self,
        page_number: str = "1",
        total_pages: str = "1",
    ) -> Dict[str, str]:
        """Build runtime placeholder dictionary for substituting `{{tokens}}` in templates."""
        if self.duration_display.strip():
            dur_str = self.duration_display.strip()
        elif self.duration_minutes is not None:
            hours, mins = divmod(self.duration_minutes, 60)
            if hours and mins:
                dur_str = f"{hours} hr {mins} min"
            elif hours:
                dur_str = f"{hours} hr{'s' if hours > 1 else ''}"
            else:
                dur_str = f"{mins} min"
        else:
            dur_str = ""

        if self.max_marks is not None:
            marks_str = (
                str(int(self.max_marks))
                if float(self.max_marks).is_integer()
                else f"{self.max_marks:g}"
            )
        else:
            marks_str = ""

        return {
            "{{exam_name}}": self.exam_name,
            "{{subject_name}}": self.subject_name,
            "{{subject_code}}": self.subject_code,
            "{{class_semester}}": self.class_semester,
            "{{exam_date}}": self.exam_date,
            "{{duration}}": dur_str,
            "{{max_marks}}": marks_str,
            "{{set_identifier}}": self.set_identifier,
            "{{page_number}}": page_number,
            "{{total_pages}}": total_pages,
        }


class LayoutSettings(BaseModel):
    """Document layout and bilingual settings with simple defaults."""

    model_config = ConfigDict(validate_assignment=True)

    columns: int = Field(default=1, ge=1, le=2)
    question_spacing_mm: float = Field(default=4.0, ge=0.0, le=50.0)
    show_marks: bool = Field(default=True)
    marks_position: MarksPosition = Field(default=MarksPosition.RIGHT_MARGIN)

    bilingual_mode: bool = Field(default=False)
    secondary_language: Optional[SecondaryLanguage] = Field(default=None)
    bilingual_layout: BilingualLayout = Field(default=BilingualLayout.SEQUENTIAL)

    base_font_family: str = Field(default="Noto Sans")
    base_font_size_pt: float = Field(default=11.0, ge=7.0, le=24.0)


class ProjectState(BaseModel):
    """Complete root state of a Question Paper project serialized inside `.qpf`."""

    model_config = ConfigDict(validate_assignment=True)

    project_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(default="Untitled Question Paper", min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    revision_number: int = Field(default=1, ge=1)

    # Embedded snapshot of the selected visual template (decoupled from global library changes)
    template_snapshot: Template = Field(default_factory=Template)

    exam_metadata: ExamMetadata = Field(default_factory=ExamMetadata)
    layout_settings: LayoutSettings = Field(default_factory=LayoutSettings)

    # Sections list (Basic Mode initializes a single transparent unsectioned default section)
    sections: List[Section] = Field(
        default_factory=lambda: [
            Section(
                title="Main",
                is_default_unsectioned=True,
                question_numbering_prefix="",
                question_numbering_suffix=".",
            )
        ]
    )

    # Optional attached examination blueprint
    blueprint: Optional[ExamBlueprint] = Field(default=None)

    @model_validator(mode="after")
    def _ensure_at_least_one_section(self) -> "ProjectState":
        if not self.sections:
            object.__setattr__(
                self,
                "sections",
                [
                    Section(
                        title="Main",
                        is_default_unsectioned=True,
                        question_numbering_prefix="",
                        question_numbering_suffix=".",
                    )
                ],
            )
        return self

    @classmethod
    def create_from_template(
        cls,
        template: Template,
        title: str = "Untitled Question Paper",
    ) -> "ProjectState":
        """Create a new ProjectState embedding a deep, isolated snapshot of `template`."""
        return cls(
            title=title,
            template_snapshot=template.create_snapshot(),
        )

    def apply_template(self, new_template: Template) -> None:
        """Hot-swap the template snapshot without losing any questions, sections, or metadata."""
        self.template_snapshot = new_template.create_snapshot()
        self.updated_at = _utc_now()

    @property
    def uses_explicit_sections(self) -> bool:
        """Return True if the teacher has configured explicit sections beyond the transparent default."""
        return len(self.sections) > 1 or not self.sections[0].is_default_unsectioned

    def all_questions_dfs(self) -> List[QuestionNode]:
        """Return all QuestionNode instances in depth-first traversal order across all sections."""
        nodes: List[QuestionNode] = []

        def _visit(node: QuestionNode) -> None:
            nodes.append(node)
            for child in node.children:
                _visit(child)

        for section in self.sections:
            for q in section.questions:
                _visit(q)
        return nodes

    def to_json_string(self, indent: int = 2) -> str:
        """Serialize the complete ProjectState AST to a UTF-8 JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json_string(cls, json_str: str) -> "ProjectState":
        """Deserialize a ProjectState AST from a JSON string."""
        return cls.model_validate_json(json_str)
