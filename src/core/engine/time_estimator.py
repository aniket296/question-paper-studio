"""Time Estimator Engine for examination completion duration analysis.

Estimates expected completion duration based on:
1. Explicit per-question `estimated_time_mins` in taxonomy metadata.
2. Heuristic baseline duration per QuestionType and marks allocation.
3. Reading time allowance for shared passages and word count.
4. Comparison against `exam_metadata.duration_minutes` with alerts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode

# Baseline estimated minutes per question type if not explicitly set
DEFAULT_TYPE_BASE_MINUTES: Dict[QuestionType, float] = {
    QuestionType.NORMAL: 3.0,
    QuestionType.MCQ: 1.5,
    QuestionType.FILL_IN_THE_BLANK: 1.0,
    QuestionType.MATCH_THE_PAIR: 2.5,
    QuestionType.TRUE_FALSE: 1.0,
    QuestionType.SHORT_ANSWER: 4.0,
    QuestionType.LONG_ANSWER: 12.0,
    QuestionType.ASSERTION_REASON: 2.0,
    QuestionType.CASE_BASED: 8.0,
    QuestionType.NUMERICAL_DYNAMIC: 4.0,
    QuestionType.ORDERING_SEQUENCING: 2.0,
    QuestionType.DIAGRAM_LABELLING: 3.0,
    QuestionType.SOURCE_BASED: 6.0,
}

WORDS_PER_MINUTE_READING = 180.0


def strip_html_tags(html: str) -> str:
    """Strip basic HTML tags to count words accurately."""
    clean = re.sub(r"<[^>]+>", " ", html)
    return " ".join(clean.split())


@dataclass
class QuestionTimeEstimate:
    """Estimated duration for an individual question."""

    question_id: str
    resolved_number: str
    question_type: QuestionType
    estimated_mins: float
    is_explicit: bool


@dataclass
class ExamTimeReport:
    """Overall examination time requirement analysis report."""

    total_estimated_minutes: float
    allocated_duration_minutes: Optional[int]
    difference_minutes: Optional[float]
    status: str  # "OK", "OVER_TIME", "UNDER_TIME", "UNCONFIGURED"
    status_message: str
    question_breakdown: List[QuestionTimeEstimate] = field(default_factory=list)


class TimeEstimator:
    """Calculates expected completion time vs exam duration."""

    @staticmethod
    def estimate_question_minutes(node: QuestionNode) -> float:
        """Estimate completion minutes for a question (and its subquestions)."""
        # If explicit time set in taxonomy metadata, use it
        if (
            node.taxonomy_metadata is not None
            and node.taxonomy_metadata.estimated_time_mins is not None
            and node.taxonomy_metadata.estimated_time_mins > 0
        ):
            base_mins = node.taxonomy_metadata.estimated_time_mins
        else:
            base_mins = DEFAULT_TYPE_BASE_MINUTES.get(node.question_type, 3.0)
            # Factor in marks if present: a 10-mark question takes more time than a 2-mark question
            if node.marks is not None and node.marks > 0:
                # heuristic: ~1.2 to 1.8 mins per mark for subjective questions
                marks_mins = node.marks * 1.5
                base_mins = max(base_mins, marks_mins * 0.75)

            # Factor in prompt reading time for longer text
            text = strip_html_tags(node.prompt_html)
            word_count = len(text.split())
            if word_count > 40:
                reading_extra = word_count / WORDS_PER_MINUTE_READING
                base_mins += reading_extra

        # If has children, accumulate children time
        if node.children:
            child_time = sum(TimeEstimator.estimate_question_minutes(ch) for ch in node.children)
            return child_time

        return round(base_mins, 1)

    @staticmethod
    def analyze_project(project: ProjectState) -> ExamTimeReport:
        """Analyze total exam time vs allocated duration."""
        breakdown: List[QuestionTimeEstimate] = []
        total_mins = 0.0

        for sec in project.sections:
            for q in sec.questions:
                is_exp = bool(
                    q.taxonomy_metadata is not None
                    and q.taxonomy_metadata.estimated_time_mins is not None
                )
                q_mins = TimeEstimator.estimate_question_minutes(q)
                total_mins += q_mins
                breakdown.append(
                    QuestionTimeEstimate(
                        question_id=q.question_id,
                        resolved_number=q.resolved_number,
                        question_type=q.question_type,
                        estimated_mins=q_mins,
                        is_explicit=is_exp,
                    )
                )

        # Include reading time for shared passages
        for sec in project.sections:
            for sp in sec.shared_passages:
                sp_text = strip_html_tags(sp.content_html)
                sp_words = len(sp_text.split())
                if sp_words > 0:
                    passage_mins = round(sp_words / WORDS_PER_MINUTE_READING, 1)
                    total_mins += passage_mins

        total_mins = round(total_mins, 1)
        allocated = project.exam_metadata.duration_minutes

        if allocated is None:
            return ExamTimeReport(
                total_estimated_minutes=total_mins,
                allocated_duration_minutes=None,
                difference_minutes=None,
                status="UNCONFIGURED",
                status_message=(
                    f"Estimated paper duration is ~{total_mins:.0f} mins. "
                    "Exam duration is not specified in exam metadata."
                ),
                question_breakdown=breakdown,
            )

        diff = total_mins - float(allocated)
        if diff > (allocated * 0.20):  # 20% overtime tolerance
            status = "OVER_TIME"
            status_msg = (
                f"Paper is likely too long: estimated {total_mins:.0f} mins vs "
                f"allocated {allocated} mins ({diff:+.0f} mins)."
            )
        elif diff < -(allocated * 0.50) and total_mins > 0:
            status = "UNDER_TIME"
            status_msg = (
                f"Paper may be too short: estimated {total_mins:.0f} mins vs "
                f"allocated {allocated} mins ({diff:+.0f} mins)."
            )
        else:
            status = "OK"
            status_msg = (
                f"Estimated time (~{total_mins:.0f} mins) aligns well with "
                f"allocated duration ({allocated} mins)."
            )

        return ExamTimeReport(
            total_estimated_minutes=total_mins,
            allocated_duration_minutes=allocated,
            difference_minutes=diff,
            status=status,
            status_message=status_msg,
            question_breakdown=breakdown,
        )
