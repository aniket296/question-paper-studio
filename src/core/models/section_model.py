"""Section, ChoiceGroup (OR / Any K of N), and SharedPassage domain models."""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.models.enums import ChoiceRuleType, NumberingStyle
from src.core.models.question_model import DiagramAttachment, QuestionNode


class ChoiceGroup(BaseModel):
    """Internal choice group linking questions via 'OR' or 'Answer any K out of N'."""

    model_config = ConfigDict(validate_assignment=True)

    choice_group_id: str = Field(default_factory=lambda: str(uuid4()))
    rule_type: ChoiceRuleType = Field(default=ChoiceRuleType.OR_PAIR)
    question_ids: List[str] = Field(default_factory=list)
    attempt_count_k: int = Field(default=1, ge=1)
    label_text: str = Field(default="OR")

    @model_validator(mode="after")
    def _validate_choice_group(self) -> "ChoiceGroup":
        if self.rule_type == ChoiceRuleType.OR_PAIR and self.attempt_count_k != 1:
            object.__setattr__(self, "attempt_count_k", 1)
        elif self.question_ids and self.attempt_count_k > len(self.question_ids):
            raise ValueError(
                f"attempt_count_k ({self.attempt_count_k}) cannot exceed total questions in group ({len(self.question_ids)})."
            )
        return self


class SharedPassage(BaseModel):
    """Reusable reading passage, case study, chart, or source stimulus shared across multiple questions."""

    model_config = ConfigDict(validate_assignment=True)

    passage_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(default="")
    instruction_text: str = Field(
        default="Read the following passage carefully and answer the questions that follow:"
    )
    content_html: str = Field(default="")
    content_secondary_html: Optional[str] = Field(default=None)
    diagrams: List[DiagramAttachment] = Field(default_factory=list)
    linked_question_ids: List[str] = Field(default_factory=list)


class Section(BaseModel):
    """Logical section of a question paper (or transparent default container in Basic Mode)."""

    model_config = ConfigDict(validate_assignment=True)

    section_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(default="Section A")
    instructions_html: str = Field(default="")
    is_default_unsectioned: bool = Field(default=False)

    # Numbering and layout overrides
    section_numbering_style: NumberingStyle = Field(default=NumberingStyle.NUMERIC)
    question_numbering_prefix: str = Field(default="Q")
    question_numbering_suffix: str = Field(default=".")
    continue_numbering_from_previous: bool = Field(default=True)
    columns_override: Optional[int] = Field(default=None, ge=1, le=2)

    # Optional section-level "Attempt any K out of N" rule across top-level questions in this section
    attempt_any_k: Optional[int] = Field(default=None, ge=1)

    questions: List[QuestionNode] = Field(default_factory=list)
    choice_groups: List[ChoiceGroup] = Field(default_factory=list)
    shared_passages: List[SharedPassage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_question_section_ids(self) -> "Section":
        def _assign(node: QuestionNode) -> None:
            object.__setattr__(node, "section_id", self.section_id)
            for ch in node.children:
                _assign(ch)

        for q in self.questions:
            _assign(q)
        return self

    def add_question(self, question: QuestionNode) -> QuestionNode:
        """Append a top-level question to this section."""
        question.parent_id = None
        question.section_id = self.section_id
        for ch in question.children:
            ch.section_id = self.section_id
        self.questions.append(question)
        return question
