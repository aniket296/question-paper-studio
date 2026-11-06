"""Optional Examination Blueprint, PatternPreset, and RubricItem domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.core.models.enums import (
    BloomLevel,
    DifficultyLevel,
    NumberingStyle,
    QuestionType,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RubricItem(BaseModel):
    """Granular marking criterion inside an evaluation rubric."""

    model_config = ConfigDict(validate_assignment=True)

    rubric_item_id: str = Field(default_factory=lambda: str(uuid4()))
    criterion: str = Field(min_length=1)
    max_marks: float = Field(ge=0.0)
    guidance_notes: str = Field(default="")


class BlueprintTargetCell(BaseModel):
    """Target marks and question count for a specific topic, type, difficulty, or Bloom level."""

    model_config = ConfigDict(validate_assignment=True)

    cell_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: Optional[str] = Field(default=None)
    question_type: Optional[QuestionType] = Field(default=None)
    difficulty: Optional[DifficultyLevel] = Field(default=None)
    bloom_level: Optional[BloomLevel] = Field(default=None)
    target_marks: float = Field(default=0.0, ge=0.0)
    target_question_count: Optional[int] = Field(default=None, ge=0)


class ExamBlueprint(BaseModel):
    """Optional Examination Blueprint matrix defining target distributions."""

    model_config = ConfigDict(validate_assignment=True)

    blueprint_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(default="Standard Examination Blueprint", min_length=1)
    created_at: datetime = Field(default_factory=_utc_now)
    total_marks_target: float = Field(default=100.0, gt=0.0)

    # Topic / unit wise marks target: {topic_name: target_marks}
    topic_marks_distribution: Dict[str, float] = Field(default_factory=dict)
    # Question type marks target: {QuestionType.value: target_marks}
    question_type_marks_distribution: Dict[str, float] = Field(default_factory=dict)
    # Difficulty percentage or marks target: {DifficultyLevel.value: target_marks}
    difficulty_marks_distribution: Dict[str, float] = Field(default_factory=dict)
    # Bloom's level marks target: {BloomLevel.value: target_marks}
    bloom_marks_distribution: Dict[str, float] = Field(default_factory=dict)

    matrix_cells: List[BlueprintTargetCell] = Field(default_factory=list)


class SectionPresetSpec(BaseModel):
    """Structural specification for a single section inside a PatternPreset."""

    model_config = ConfigDict(validate_assignment=True)

    title: str = Field(default="Section A")
    instructions_html: str = Field(default="")
    default_question_type: QuestionType = Field(default=QuestionType.NORMAL)
    question_count: int = Field(default=5, ge=1)
    marks_per_question: float = Field(default=2.0, ge=0.0)
    attempt_any_k: Optional[int] = Field(default=None, ge=1)
    numbering_style: NumberingStyle = Field(default=NumberingStyle.NUMERIC)


class PatternPreset(BaseModel):
    """Reusable structural examination preset (independent of visual header/footer templates)."""

    model_config = ConfigDict(validate_assignment=True)

    preset_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(default="80-Mark Semester Pattern", min_length=1)
    description: str = Field(default="")
    duration_minutes: int = Field(default=180, ge=5)
    max_marks: float = Field(default=80.0, gt=0.0)
    sections: List[SectionPresetSpec] = Field(default_factory=list)
