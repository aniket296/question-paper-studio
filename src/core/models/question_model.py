"""Recursive QuestionNode AST and polymorphic type payload models."""

from __future__ import annotations

from typing import Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.models.enums import (
    BloomLevel,
    DifficultyLevel,
    FillBlankMode,
    MCQOptionLayout,
    NumberingStyle,
    QuestionType,
    TextAlignment,
)


def _index_to_alpha_label(index: int) -> str:
    """Convert 0-based index into spreadsheet/option label (A, B, C... Z, AA...)."""
    result = ""
    n = index
    while n >= 0:
        result = chr(ord("A") + (n % 26)) + result
        n = (n // 26) - 1
    return result


class DiagramAttachment(BaseModel):
    """Diagram or image attached to a question node."""

    model_config = ConfigDict(validate_assignment=True)

    diagram_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_path: str = Field(min_length=1)
    width_mm: float = Field(default=60.0, gt=5.0, le=400.0)
    height_mm: float = Field(default=40.0, gt=5.0, le=400.0)
    alignment: TextAlignment = Field(default=TextAlignment.CENTER)
    caption: str = Field(default="")
    dpi: int = Field(default=300, ge=36)


class StepPoint(BaseModel):
    """Individual step mark inside a question's marking scheme / rubric."""

    model_config = ConfigDict(validate_assignment=True)

    description: str = Field(min_length=1)
    marks: float = Field(ge=0.0)


class MarkingScheme(BaseModel):
    """Optional marking rubric and model answer for a question."""

    model_config = ConfigDict(validate_assignment=True)

    model_answer_html: str = Field(default="")
    step_points: List[StepPoint] = Field(default_factory=list)
    alternative_answers: List[str] = Field(default_factory=list)
    rubric_notes: str = Field(default="")


class TaxonomyMetadata(BaseModel):
    """Optional academic classification metadata (progressive disclosure)."""

    model_config = ConfigDict(validate_assignment=True)

    subject: Optional[str] = Field(default=None)
    unit: Optional[str] = Field(default=None)
    chapter: Optional[str] = Field(default=None)
    topic: Optional[str] = Field(default=None)
    difficulty: Optional[DifficultyLevel] = Field(default=None)
    bloom_level: Optional[BloomLevel] = Field(default=None)
    learning_outcome: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    estimated_time_mins: Optional[float] = Field(default=None, ge=0.0)


# ============================================================================
# Core Question Type Payloads (4 Core Types)
# ============================================================================


class NormalQuestionData(BaseModel):
    """Payload for a standard descriptive/normal question."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="NORMAL")


class MCQOption(BaseModel):
    """A single option inside a Multiple Choice Question."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    text_html: str = Field(default="")
    is_correct: bool = Field(default=False)
    label: str = Field(default="A")


class MCQData(BaseModel):
    """Payload for Multiple Choice Questions (starts with 1 box in UI; requires >=2 to finalize)."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="MCQ")
    options: List[MCQOption] = Field(
        default_factory=lambda: [MCQOption(text_html="", is_correct=False, label="A")]
    )
    allow_multiple_correct: bool = Field(default=False)
    option_layout: MCQOptionLayout = Field(default=MCQOptionLayout.GRID_2X2)

    @model_validator(mode="after")
    def _relabel_options(self) -> "MCQData":
        self.relabel_options()
        return self

    def relabel_options(self) -> None:
        """Auto-label options sequentially as A, B, C, D..."""
        for idx, opt in enumerate(self.options):
            object.__setattr__(opt, "label", _index_to_alpha_label(idx))

    def add_option(self, text_html: str = "", is_correct: bool = False) -> MCQOption:
        """Append a new option box and update labels."""
        new_opt = MCQOption(
            text_html=text_html,
            is_correct=is_correct,
            label=_index_to_alpha_label(len(self.options)),
        )
        self.options.append(new_opt)
        self.relabel_options()
        return new_opt

    def remove_option(self, option_id: str) -> None:
        """Remove an option by ID and re-sequence A, B, C, D labels."""
        self.options = [opt for opt in self.options if opt.id != option_id]
        self.relabel_options()

    def validate_for_finalization(self) -> List[str]:
        """Validate that the MCQ has at least 2 non-empty options and valid correct answer selection."""
        errors: List[str] = []
        if len(self.options) < 2:
            errors.append("MCQ requires at least 2 options before finalization.")
        non_empty = [o for o in self.options if o.text_html.strip()]
        if len(non_empty) < 2:
            errors.append("At least 2 MCQ options must contain text.")
        correct_count = sum(1 for o in self.options if o.is_correct)
        if not self.allow_multiple_correct and correct_count > 1:
            errors.append("Multiple correct options marked while allow_multiple_correct is False.")
        return errors


class BlankItem(BaseModel):
    """Ground-truth answer for a specific blank placeholder in a Fill-in-the-Blank question."""

    model_config = ConfigDict(validate_assignment=True)

    blank_index: int = Field(ge=1)
    correct_answer: str = Field(default="")


class FillBlankData(BaseModel):
    """Payload for Fill in the Blank questions (with or without options/word bank)."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="FILL_IN_THE_BLANK")
    mode: FillBlankMode = Field(default=FillBlankMode.WITHOUT_OPTIONS)
    blanks: List[BlankItem] = Field(
        default_factory=lambda: [BlankItem(blank_index=1, correct_answer="")]
    )
    word_bank_options: List[str] = Field(default_factory=list)


class MatchPairRow(BaseModel):
    """A single row in a Match the Pair table."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    col_a_html: str = Field(default="")
    col_b_html: str = Field(default="")
    shuffled_col_b_index: Optional[int] = Field(default=None)


class MatchPairData(BaseModel):
    """Payload for Match the Pair questions (defaults to 2 rows; extendable/removable)."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="MATCH_THE_PAIR")
    col_a_header: str = Field(default="Column A")
    col_b_header: str = Field(default="Column B")
    rows: List[MatchPairRow] = Field(
        default_factory=lambda: [
            MatchPairRow(col_a_html="", col_b_html="", shuffled_col_b_index=0),
            MatchPairRow(col_a_html="", col_b_html="", shuffled_col_b_index=1),
        ]
    )
    shuffle_col_b: bool = Field(default=False)

    def add_row(self, col_a_html: str = "", col_b_html: str = "") -> MatchPairRow:
        """Append a new pair row to the table."""
        idx = len(self.rows)
        row = MatchPairRow(col_a_html=col_a_html, col_b_html=col_b_html, shuffled_col_b_index=idx)
        self.rows.append(row)
        return row

    def remove_row(self, row_id: str) -> None:
        """Remove a pair row by ID, preserving at least 1 row."""
        if len(self.rows) <= 1:
            raise ValueError("Match the Pair table must retain at least 1 row.")
        self.rows = [r for r in self.rows if r.id != row_id]
        for idx, r in enumerate(self.rows):
            if r.shuffled_col_b_index is None or r.shuffled_col_b_index >= len(self.rows):
                r.shuffled_col_b_index = idx

    def ground_truth_mapping(self) -> Dict[int, int]:
        """Return 1-based Column A row index -> 1-based displayed Column B index for the answer key."""
        mapping: Dict[int, int] = {}
        # Each row i has ground-truth partner `rows[i].col_b_html`.
        # When `shuffled_col_b_index` specifies where row i's col_b is displayed (0-based):
        for idx, row in enumerate(self.rows):
            displayed_idx = row.shuffled_col_b_index if row.shuffled_col_b_index is not None else idx
            mapping[idx + 1] = displayed_idx + 1
        return mapping


# ============================================================================
# Optional Question Type Payloads (9 Progressive Disclosure Types)
# ============================================================================


class TrueFalseData(BaseModel):
    """Payload for True / False questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="TRUE_FALSE")
    correct_is_true: Optional[bool] = Field(default=True)
    require_justification: bool = Field(default=False)


class ShortAnswerData(BaseModel):
    """Payload for Short Answer questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="SHORT_ANSWER")
    word_limit: Optional[int] = Field(default=50, ge=1)
    expected_keywords: List[str] = Field(default_factory=list)


class LongAnswerData(BaseModel):
    """Payload for Long / Essay Answer questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="LONG_ANSWER")
    word_limit: Optional[int] = Field(default=250, ge=1)
    evaluation_criteria: List[str] = Field(default_factory=list)


class AssertionReasonData(BaseModel):
    """Payload for Assertion & Reason questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="ASSERTION_REASON")
    assertion_html: str = Field(default="")
    reason_html: str = Field(default="")
    options: List[str] = Field(
        default_factory=lambda: [
            "Both Assertion (A) and Reason (R) are true and R is the correct explanation of A.",
            "Both Assertion (A) and Reason (R) are true, but R is not the correct explanation of A.",
            "Assertion (A) is true, but Reason (R) is false.",
            "Assertion (A) is false, but Reason (R) is true.",
        ]
    )
    correct_option_index: int = Field(default=0, ge=0, le=3)


class CaseBasedData(BaseModel):
    """Payload for Case-based / Comprehension questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="CASE_BASED")
    case_title: str = Field(default="")
    case_passage_html: str = Field(default="")


class NumericVariableRange(BaseModel):
    """Range specification for a parameterized variable in a Dynamic Numerical question."""

    model_config = ConfigDict(validate_assignment=True)

    min_val: float = Field(default=1.0)
    max_val: float = Field(default=10.0)
    precision: int = Field(default=0, ge=0, le=6)
    step: Optional[float] = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> "NumericVariableRange":
        if self.max_val < self.min_val:
            raise ValueError("max_val must be >= min_val in NumericVariableRange.")
        return self


class NumericalDynamicData(BaseModel):
    """Payload for Dynamic / Parameterized Numerical questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="NUMERICAL_DYNAMIC")
    variables: Dict[str, NumericVariableRange] = Field(default_factory=dict)
    formula_expr: str = Field(default="")
    unit: str = Field(default="")
    answer_tolerance: float = Field(default=0.01, ge=0.0)
    instantiated_values: Dict[str, float] = Field(default_factory=dict)
    computed_answer: Optional[float] = Field(default=None)


class OrderingItem(BaseModel):
    """An item in an Ordering / Sequencing question."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    text_html: str = Field(default="")
    correct_position: int = Field(default=1, ge=1)


class OrderingSequencingData(BaseModel):
    """Payload for Ordering / Sequencing questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="ORDERING_SEQUENCING")
    items: List[OrderingItem] = Field(default_factory=list)
    displayed_order_ids: List[str] = Field(default_factory=list)


class DiagramLabelHotspot(BaseModel):
    """A numbered callout hotspot on a Diagram Labelling question."""

    model_config = ConfigDict(validate_assignment=True)

    label_id: str = Field(default="1")
    x_percent: float = Field(default=50.0, ge=0.0, le=100.0)
    y_percent: float = Field(default=50.0, ge=0.0, le=100.0)
    correct_term: str = Field(default="")


class DiagramLabellingData(BaseModel):
    """Payload for Diagram Labelling questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="DIAGRAM_LABELLING")
    diagram_asset_path: str = Field(default="")
    hotspots: List[DiagramLabelHotspot] = Field(default_factory=list)


class SourceBasedData(BaseModel):
    """Payload for Source-based / Extract / Picture / Data-table questions."""

    model_config = ConfigDict(validate_assignment=True)

    kind: str = Field(default="SOURCE_BASED")
    source_excerpt_html: str = Field(default="")
    source_citation: str = Field(default="")


QuestionTypeDataUnion = Union[
    NormalQuestionData,
    MCQData,
    FillBlankData,
    MatchPairData,
    TrueFalseData,
    ShortAnswerData,
    LongAnswerData,
    AssertionReasonData,
    CaseBasedData,
    NumericalDynamicData,
    OrderingSequencingData,
    DiagramLabellingData,
    SourceBasedData,
]


def default_type_data_for(qtype: QuestionType) -> QuestionTypeDataUnion:
    """Instantiate the default polymorphic payload corresponding to `qtype`."""
    mapping = {
        QuestionType.NORMAL: NormalQuestionData,
        QuestionType.MCQ: MCQData,
        QuestionType.FILL_IN_THE_BLANK: FillBlankData,
        QuestionType.MATCH_THE_PAIR: MatchPairData,
        QuestionType.TRUE_FALSE: TrueFalseData,
        QuestionType.SHORT_ANSWER: ShortAnswerData,
        QuestionType.LONG_ANSWER: LongAnswerData,
        QuestionType.ASSERTION_REASON: AssertionReasonData,
        QuestionType.CASE_BASED: CaseBasedData,
        QuestionType.NUMERICAL_DYNAMIC: NumericalDynamicData,
        QuestionType.ORDERING_SEQUENCING: OrderingSequencingData,
        QuestionType.DIAGRAM_LABELLING: DiagramLabellingData,
        QuestionType.SOURCE_BASED: SourceBasedData,
    }
    return mapping[qtype]()


class QuestionNode(BaseModel):
    """Recursive Question AST node supporting arbitrary hierarchy depth."""

    model_config = ConfigDict(validate_assignment=True)

    question_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_id: Optional[str] = Field(default=None)
    section_id: Optional[str] = Field(default=None)

    question_type: QuestionType = Field(default=QuestionType.NORMAL)
    numbering_override: Optional[str] = Field(default=None)
    resolved_number: str = Field(default="")
    child_numbering_style: NumberingStyle = Field(default=NumberingStyle.LOWER_ALPHA)
    custom_child_prefix: str = Field(default="(")
    custom_child_suffix: str = Field(default=")")

    prompt_html: str = Field(default="")
    prompt_secondary_html: Optional[str] = Field(default=None)
    diagrams: List[DiagramAttachment] = Field(default_factory=list)
    shared_passage_id: Optional[str] = Field(default=None)

    marks: Optional[float] = Field(default=None, ge=0.0)
    choice_group_id: Optional[str] = Field(default=None)
    answer_space_lines: int = Field(default=0, ge=0, le=100)
    page_break_before: bool = Field(default=False)

    type_data: Optional[QuestionTypeDataUnion] = Field(default=None)
    marking_scheme: Optional[MarkingScheme] = Field(default=None)
    taxonomy_metadata: Optional[TaxonomyMetadata] = Field(default=None)

    children: List["QuestionNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ensure_type_data_and_parent_links(self) -> "QuestionNode":
        if self.type_data is None or self.type_data.kind != self.question_type.value:
            object.__setattr__(self, "type_data", default_type_data_for(self.question_type))
        for child in self.children:
            object.__setattr__(child, "parent_id", self.question_id)
            if self.section_id and not child.section_id:
                object.__setattr__(child, "section_id", self.section_id)
        return self

    def validate_node(self, finalize: bool = False) -> List[str]:
        """Validate this question node and its children (enforcing MCQ >=2 options on finalize)."""
        errors: List[str] = []
        if self.question_type == QuestionType.MCQ and isinstance(self.type_data, MCQData):
            if finalize:
                errors.extend(self.type_data.validate_for_finalization())
        for child in self.children:
            errors.extend(child.validate_node(finalize=finalize))
        return errors

    def add_child(self, child: "QuestionNode") -> "QuestionNode":
        """Attach a child subquestion to this question node."""
        child.parent_id = self.question_id
        child.section_id = self.section_id
        self.children.append(child)
        return child

    def clone_with_new_ids(self) -> "QuestionNode":
        """Create a deep copy of this question subtree with newly generated UUIDs."""
        cloned = self.model_copy(deep=True)

        def _reid(node: QuestionNode, parent_id: Optional[str]) -> None:
            node.question_id = str(uuid4())
            node.parent_id = parent_id
            for diag in node.diagrams:
                diag.diagram_id = str(uuid4())
            if isinstance(node.type_data, MCQData):
                for opt in node.type_data.options:
                    opt.id = str(uuid4())
            elif isinstance(node.type_data, MatchPairData):
                for row in node.type_data.rows:
                    row.id = str(uuid4())
            for ch in node.children:
                _reid(ch, node.question_id)

        _reid(cloned, self.parent_id)
        return cloned


QuestionNode.model_rebuild()
