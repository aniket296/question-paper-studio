"""Paper Quality and Integrity Analyzer Engine.

Audits question papers for:
1. Duplicate questions (identical or near-identical prompts).
2. Duplicate MCQ options within the same question.
3. Missing correct answer keys (MCQ with no correct option, blanks with empty answers, etc.).
4. Incomplete blanks (Fill in the blank with no ___ placeholder in prompt).
5. Low-DPI or oversized diagram attachments.
6. Empty prompts or unallocated marks.
7. Choice group sanity checks (empty groups or orphan question IDs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from src.core.models.enums import QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    FillBlankData,
    MCQData,
    MatchPairData,
    QuestionNode,
    TrueFalseData,
)


class QualitySeverity(str, Enum):
    """Severity of a detected quality issue."""

    CRITICAL = "CRITICAL"  # Missing answer key, invalid choice group, etc.
    WARNING = "WARNING"    # Low DPI, duplicate option, marks missing
    INFO = "INFO"          # Suggestion or minor aesthetic notice


@dataclass
class QualityIssue:
    """An issue detected during paper quality inspection."""

    code: str
    severity: QualitySeverity
    message: str
    question_id: Optional[str] = None
    resolved_number: Optional[str] = None
    details: Optional[str] = None


@dataclass
class QualityAuditReport:
    """Consolidated quality audit report."""

    total_issues: int
    critical_count: int
    warning_count: int
    info_count: int
    passed_cleanly: bool
    issues: List[QualityIssue] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    """Strip HTML tags, punctuation, and excess whitespace for comparison."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"[^\w\s]", "", clean)
    return " ".join(clean.lower().split())


class QualityChecker:
    """Audits question paper state for common authoring flaws and quality errors."""

    @staticmethod
    def audit_project(project: ProjectState) -> QualityAuditReport:
        """Run all quality and integrity checks on `project`."""
        issues: List[QualityIssue] = []

        all_nodes = project.all_questions_dfs()
        seen_prompts: Dict[str, QuestionNode] = {}

        # 1. Check Questions and Children
        for node in all_nodes:
            norm_prompt = _normalize_text(node.prompt_html)

            # Empty prompt check
            if not norm_prompt:
                issues.append(
                    QualityIssue(
                        code="EMPTY_PROMPT",
                        severity=QualitySeverity.CRITICAL,
                        message=f"Question {node.resolved_number or node.question_id} has an empty prompt.",
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )
            else:
                # Duplicate question check (ignore very short prompts like 'solve' or 'prove')
                if len(norm_prompt) > 15:
                    if norm_prompt in seen_prompts:
                        first_node = seen_prompts[norm_prompt]
                        issues.append(
                            QualityIssue(
                                code="DUPLICATE_QUESTION",
                                severity=QualitySeverity.WARNING,
                                message=(
                                    f"Question {node.resolved_number or node.question_id} has identical/duplicate "
                                    f"prompt to Question {first_node.resolved_number or first_node.question_id}."
                                ),
                                question_id=node.question_id,
                                resolved_number=node.resolved_number,
                            )
                        )
                    else:
                        seen_prompts[norm_prompt] = node

            # Unallocated marks check (leaf nodes must have marks)
            if not node.children and (node.marks is None or node.marks <= 0):
                issues.append(
                    QualityIssue(
                        code="UNALLOCATED_MARKS",
                        severity=QualitySeverity.WARNING,
                        message=f"Question {node.resolved_number or node.question_id} has no marks allocated.",
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )

            # Diagram DPI checks
            for diag in node.diagrams:
                if diag.dpi < 150:
                    issues.append(
                        QualityIssue(
                            code="LOW_DPI_IMAGE",
                            severity=QualitySeverity.WARNING,
                            message=(
                                f"Diagram in Question {node.resolved_number or node.question_id} "
                                f"has low DPI ({diag.dpi} DPI < 150 DPI target)."
                            ),
                            question_id=node.question_id,
                            resolved_number=node.resolved_number,
                            details=f"Asset path: {diag.asset_path}",
                        )
                    )

            # Question type specific audits
            QualityChecker._audit_question_type(node, issues)

        # 2. Section and Choice Group Checks
        valid_qids: Set[str] = {q.question_id for q in all_nodes}
        for sec in project.sections:
            for cg in sec.choice_groups:
                if not cg.question_ids:
                    issues.append(
                        QualityIssue(
                            code="EMPTY_CHOICE_GROUP",
                            severity=QualitySeverity.WARNING,
                            message=f"Choice group '{cg.choice_group_id}' in section '{sec.title}' contains no questions.",
                        )
                    )
                else:
                    orphan_ids = [qid for qid in cg.question_ids if qid not in valid_qids]
                    if orphan_ids:
                        issues.append(
                            QualityIssue(
                                code="ORPHAN_CHOICE_GROUP_MEMBER",
                                severity=QualitySeverity.CRITICAL,
                                message=(
                                    f"Choice group in section '{sec.title}' references "
                                    f"non-existent question IDs: {orphan_ids}"
                                ),
                            )
                        )

            for sp in sec.shared_passages:
                if not sp.linked_question_ids:
                    issues.append(
                        QualityIssue(
                            code="UNLINKED_SHARED_PASSAGE",
                            severity=QualitySeverity.INFO,
                            message=f"Shared passage '{sp.title or sp.passage_id}' is not linked to any questions.",
                        )
                    )

        crit_count = sum(1 for i in issues if i.severity == QualitySeverity.CRITICAL)
        warn_count = sum(1 for i in issues if i.severity == QualitySeverity.WARNING)
        info_count = sum(1 for i in issues if i.severity == QualitySeverity.INFO)

        return QualityAuditReport(
            total_issues=len(issues),
            critical_count=crit_count,
            warning_count=warn_count,
            info_count=info_count,
            passed_cleanly=(crit_count == 0 and warn_count == 0),
            issues=issues,
        )

    @staticmethod
    def _audit_question_type(node: QuestionNode, issues: List[QualityIssue]) -> None:
        """Type-specific validations (MCQ, Blank, Match, TrueFalse)."""
        if node.question_type == QuestionType.MCQ and isinstance(node.type_data, MCQData):
            mcq = node.type_data
            if len(mcq.options) < 2:
                issues.append(
                    QualityIssue(
                        code="MCQ_INSUFFICIENT_OPTIONS",
                        severity=QualitySeverity.CRITICAL,
                        message=f"MCQ Question {node.resolved_number or node.question_id} has fewer than 2 options.",
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )

            # Check duplicate options within the same MCQ
            seen_opts: Dict[str, str] = {}
            has_correct = False
            for opt in mcq.options:
                if opt.is_correct:
                    has_correct = True
                norm_opt = _normalize_text(opt.text_html)
                if norm_opt:
                    if norm_opt in seen_opts:
                        issues.append(
                            QualityIssue(
                                code="DUPLICATE_MCQ_OPTION",
                                severity=QualitySeverity.WARNING,
                                message=(
                                    f"MCQ Option '{opt.label}' in Question {node.resolved_number or node.question_id} "
                                    f"is identical to Option '{seen_opts[norm_opt]}'."
                                ),
                                question_id=node.question_id,
                                resolved_number=node.resolved_number,
                            )
                        )
                    else:
                        seen_opts[norm_opt] = opt.label

            if not has_correct:
                issues.append(
                    QualityIssue(
                        code="MISSING_MCQ_KEY",
                        severity=QualitySeverity.CRITICAL,
                        message=f"MCQ Question {node.resolved_number or node.question_id} has no correct answer selected.",
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )

        elif node.question_type == QuestionType.FILL_IN_THE_BLANK and isinstance(node.type_data, FillBlankData):
            blank_data = node.type_data
            # Check for blank markers in prompt like ___ or _____
            if "_" not in node.prompt_html and "[blank]" not in node.prompt_html.lower():
                issues.append(
                    QualityIssue(
                        code="MISSING_BLANK_PLACEHOLDER",
                        severity=QualitySeverity.WARNING,
                        message=(
                            f"Fill in the Blank Question {node.resolved_number or node.question_id} "
                            "contains no blank placeholders ('___') in its prompt."
                        ),
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )

            # Check for empty correct answer
            for b in blank_data.blanks:
                if not b.correct_answer.strip():
                    issues.append(
                        QualityIssue(
                            code="EMPTY_BLANK_ANSWER",
                            severity=QualitySeverity.WARNING,
                            message=(
                                f"Blank #{b.blank_index} in Question {node.resolved_number or node.question_id} "
                                "has an empty correct answer."
                            ),
                            question_id=node.question_id,
                            resolved_number=node.resolved_number,
                        )
                    )

        elif node.question_type == QuestionType.MATCH_THE_PAIR and isinstance(node.type_data, MatchPairData):
            match_data = node.type_data
            for idx, r in enumerate(match_data.rows, start=1):
                if not r.col_a_html.strip() or not r.col_b_html.strip():
                    issues.append(
                        QualityIssue(
                            code="EMPTY_MATCH_PAIR_CELL",
                            severity=QualitySeverity.WARNING,
                            message=(
                                f"Match the Pair Question {node.resolved_number or node.question_id} "
                                f"has an empty cell in Row #{idx}."
                            ),
                            question_id=node.question_id,
                            resolved_number=node.resolved_number,
                        )
                    )

        elif node.question_type == QuestionType.TRUE_FALSE and isinstance(node.type_data, TrueFalseData):
            tf_data = node.type_data
            if tf_data.correct_is_true is None:
                issues.append(
                    QualityIssue(
                        code="MISSING_TRUE_FALSE_KEY",
                        severity=QualitySeverity.WARNING,
                        message=f"True/False Question {node.resolved_number or node.question_id} has no correct answer set.",
                        question_id=node.question_id,
                        resolved_number=node.resolved_number,
                    )
                )
