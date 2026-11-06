"""Domain enumerations for Question Paper Studio."""

from __future__ import annotations

from enum import Enum
from typing import Tuple


class PageSize(str, Enum):
    """Standard and custom printable page sizes."""

    A4 = "A4"
    A3 = "A3"
    LETTER = "Letter"
    CUSTOM = "Custom"

    @property
    def default_dimensions_mm(self) -> Tuple[float, float]:
        """Return (width_mm, height_mm) in portrait orientation."""
        mapping = {
            PageSize.A4: (210.0, 297.0),
            PageSize.A3: (297.0, 420.0),
            PageSize.LETTER: (215.9, 279.4),
            PageSize.CUSTOM: (210.0, 297.0),
        }
        return mapping[self]


class Orientation(str, Enum):
    """Page orientation."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class CanvasElementType(str, Enum):
    """Element types allowed in the Header and Footer Template Designer Canvas."""

    TEXT = "text"
    IMAGE = "image"
    LINE = "line"
    BORDER = "border"
    PAGE_NUMBER = "page_number"


class TextAlignment(str, Enum):
    """Horizontal alignment for canvas elements, paragraphs, and diagrams."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class QuestionType(str, Enum):
    """Supported question types (4 Core by default + 9 Optional via Progressive Disclosure)."""

    # Core Types (Visible by default in Basic Mode)
    NORMAL = "NORMAL"
    MCQ = "MCQ"
    FILL_IN_THE_BLANK = "FILL_IN_THE_BLANK"
    MATCH_THE_PAIR = "MATCH_THE_PAIR"

    # Optional Additional Types (Shown when enabled via Progressive Disclosure)
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"
    LONG_ANSWER = "LONG_ANSWER"
    ASSERTION_REASON = "ASSERTION_REASON"
    CASE_BASED = "CASE_BASED"
    NUMERICAL_DYNAMIC = "NUMERICAL_DYNAMIC"
    ORDERING_SEQUENCING = "ORDERING_SEQUENCING"
    DIAGRAM_LABELLING = "DIAGRAM_LABELLING"
    SOURCE_BASED = "SOURCE_BASED"

    @classmethod
    def core_types(cls) -> Tuple["QuestionType", ...]:
        """Return the 4 default question types always shown in Basic Mode."""
        return (
            cls.NORMAL,
            cls.MCQ,
            cls.FILL_IN_THE_BLANK,
            cls.MATCH_THE_PAIR,
        )

    @classmethod
    def optional_types(cls) -> Tuple["QuestionType", ...]:
        """Return the 9 optional question types revealed via progressive disclosure."""
        return (
            cls.TRUE_FALSE,
            cls.SHORT_ANSWER,
            cls.LONG_ANSWER,
            cls.ASSERTION_REASON,
            cls.CASE_BASED,
            cls.NUMERICAL_DYNAMIC,
            cls.ORDERING_SEQUENCING,
            cls.DIAGRAM_LABELLING,
            cls.SOURCE_BASED,
        )

    @property
    def is_core(self) -> bool:
        """Return True if this question type is one of the 4 Basic Mode core types."""
        return self in self.core_types()


class NumberingStyle(str, Enum):
    """Hierarchical numbering styles for sections, questions, and subquestions."""

    NUMERIC = "NUMERIC"          # 1, 2, 3
    UPPER_ALPHA = "UPPER_ALPHA"  # A, B, C
    LOWER_ALPHA = "LOWER_ALPHA"  # a, b, c
    UPPER_ROMAN = "UPPER_ROMAN"  # I, II, III
    LOWER_ROMAN = "LOWER_ROMAN"  # i, ii, iii
    CUSTOM = "CUSTOM"            # Custom prefix/suffix or manual override


class MCQOptionLayout(str, Enum):
    """Visual layout for MCQ options on the printed page."""

    INLINE = "inline"
    GRID_2X2 = "grid_2x2"
    STACKED = "stacked"


class FillBlankMode(str, Enum):
    """Sub-modes for Fill in the Blank questions."""

    WITHOUT_OPTIONS = "without_options"
    WITH_OPTIONS = "with_options"


class ChoiceRuleType(str, Enum):
    """Internal choice rule types for sections and question groups."""

    OR_PAIR = "OR"
    ANY_K_OF_N = "ANY_K_OF_N"


class DifficultyLevel(str, Enum):
    """Optional question difficulty classification."""

    EASY = "Easy"
    MODERATE = "Moderate"
    DIFFICULT = "Difficult"


class BloomLevel(str, Enum):
    """Optional Bloom's Taxonomy cognitive levels."""

    REMEMBER = "Remember"
    UNDERSTAND = "Understand"
    APPLY = "Apply"
    ANALYZE = "Analyze"
    EVALUATE = "Evaluate"
    CREATE = "Create"


class MarksPosition(str, Enum):
    """Placement of question marks in the rendered output."""

    RIGHT_MARGIN = "right_margin"
    INLINE_END = "inline_end"


class SecondaryLanguage(str, Enum):
    """Supported secondary languages for Bilingual Mode."""

    HINDI = "hi"
    MARATHI = "mr"


class BilingualLayout(str, Enum):
    """Layout arrangement when Bilingual Mode is enabled."""

    SEQUENTIAL = "sequential"
    SIDE_BY_SIDE = "side_by_side"


class CandidateFieldType(str, Enum):
    """Standard candidate info fields that can be enabled in the header box."""

    STUDENT_NAME = "Student Name"
    ROLL_NO = "Roll No"
    SEAT_NO = "Seat No"
    REG_NO = "Reg No"
    STUDENT_SIGNATURE = "Student Signature"
    INVIGILATOR_SIGNATURE = "Invigilator Signature"
