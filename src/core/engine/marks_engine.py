"""Marks Calculation and Internal Choice Resolution Engine.

Implements:
1. Section-wise and total paper marks computation.
2. Parent-child deduplication rule: if a parent question has children with assigned marks,
   the parent's effective mark is the sum of its children (never double-counted).
3. Internal choices rule:
   - OR pairs: adds max/representative mark of the choice (e.g. 5 Marks OR 5 Marks -> 5.0, not 10.0).
   - Answer any K out of N: sums the top K marks from the choice group.
4. Section-level 'Attempt any K out of N' top-level question rule.
5. Max marks comparison and discrepancy warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.core.models.enums import ChoiceRuleType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import ChoiceGroup, Section


@dataclass
class QuestionMarksSummary:
    """Detailed marks breakdown for an individual QuestionNode."""

    question_id: str
    assigned_marks: Optional[float]
    effective_marks: float
    is_parent_composite: bool
    children_marks_sum: float
    choice_group_id: Optional[str] = None


@dataclass
class SectionMarksSummary:
    """Marks breakdown for an entire section."""

    section_id: str
    section_title: str
    total_available_marks: float  # Sum if student answers everything
    total_effective_marks: float  # Real exam marks considering internal choices / rules
    question_summaries: List[QuestionMarksSummary] = field(default_factory=list)


@dataclass
class PaperMarksReport:
    """Overall examination paper marks audit report."""

    total_effective_marks: float
    total_available_marks: float
    max_marks_target: Optional[float]
    has_discrepancy: bool
    discrepancy_delta: float
    discrepancy_message: Optional[str]
    section_reports: List[SectionMarksSummary] = field(default_factory=list)


class MarksEngine:
    """Calculates section-wise and total marks adhering to parent-child deduplication and choice rules."""

    @staticmethod
    def calculate_question_effective_marks(node: QuestionNode) -> QuestionMarksSummary:
        """Calculate effective marks for `node`, resolving parent-child aggregation.

        Parent-Child Rule:
        If a parent node has children with marks assigned, the parent's effective mark is
        the sum of its children's effective marks. The parent's explicit node.marks is NOT added.
        If children have no marks or no children exist, node.marks is used.
        """
        if node.children:
            child_summaries = [
                MarksEngine.calculate_question_effective_marks(child)
                for child in node.children
            ]
            children_sum = sum(cs.effective_marks for cs in child_summaries)
            if children_sum > 0:
                return QuestionMarksSummary(
                    question_id=node.question_id,
                    assigned_marks=node.marks,
                    effective_marks=children_sum,
                    is_parent_composite=True,
                    children_marks_sum=children_sum,
                    choice_group_id=node.choice_group_id,
                )

        eff = float(node.marks) if node.marks is not None else 0.0
        return QuestionMarksSummary(
            question_id=node.question_id,
            assigned_marks=node.marks,
            effective_marks=eff,
            is_parent_composite=False,
            children_marks_sum=0.0,
            choice_group_id=node.choice_group_id,
        )

    @staticmethod
    def calculate_section_marks(section: Section) -> SectionMarksSummary:
        """Calculate marks for a section considering ChoiceGroups and section-level attempt rules."""
        q_summaries: List[QuestionMarksSummary] = []
        q_map: Dict[str, QuestionMarksSummary] = {}

        for q in section.questions:
            q_sum = MarksEngine.calculate_question_effective_marks(q)
            q_summaries.append(q_sum)
            q_map[q.question_id] = q_sum

        total_available = sum(qs.effective_marks for qs in q_summaries)

        # Process ChoiceGroups defined in the section
        handled_in_groups: Set[str] = set()
        group_effective_sum = 0.0

        for cg in section.choice_groups:
            group_q_sums = [q_map[qid] for qid in cg.question_ids if qid in q_map]
            if not group_q_sums:
                continue

            for qid in cg.question_ids:
                handled_in_groups.add(qid)

            marks_list = [gqs.effective_marks for gqs in group_q_sums]
            marks_list.sort(reverse=True)

            if cg.rule_type == ChoiceRuleType.OR_PAIR:
                # For an OR pair, effective marks is the maximum mark of the options (usually identical)
                group_effective_sum += marks_list[0] if marks_list else 0.0
            elif cg.rule_type == ChoiceRuleType.ANY_K_OF_N:
                k = min(cg.attempt_count_k, len(marks_list))
                group_effective_sum += sum(marks_list[:k])

        # Top-level questions not part of any explicit ChoiceGroup
        ungrouped_q_sums = [
            qs for qs in q_summaries if qs.question_id not in handled_in_groups
        ]

        if section.attempt_any_k is not None and section.attempt_any_k < len(ungrouped_q_sums):
            # Section-level 'Attempt any K out of N' applies to ungrouped questions
            ungrouped_marks = [u.effective_marks for u in ungrouped_q_sums]
            ungrouped_marks.sort(reverse=True)
            k = section.attempt_any_k
            effective_ungrouped = sum(ungrouped_marks[:k])
        else:
            effective_ungrouped = sum(u.effective_marks for u in ungrouped_q_sums)

        total_effective = group_effective_sum + effective_ungrouped

        return SectionMarksSummary(
            section_id=section.section_id,
            section_title=section.title,
            total_available_marks=total_available,
            total_effective_marks=total_effective,
            question_summaries=q_summaries,
        )

    @staticmethod
    def audit_project(project: ProjectState) -> PaperMarksReport:
        """Alias for audit_project_marks."""
        return MarksEngine.audit_project_marks(project)

    @staticmethod
    def audit_project_marks(project: ProjectState) -> PaperMarksReport:
        """Audit paper marks and produce comprehensive PaperMarksReport with discrepancy checks."""
        sec_reports: List[SectionMarksSummary] = []
        for sec in project.sections:
            sec_reports.append(MarksEngine.calculate_section_marks(sec))

        total_eff = sum(sr.total_effective_marks for sr in sec_reports)
        total_avail = sum(sr.total_available_marks for sr in sec_reports)
        target = project.exam_metadata.max_marks

        has_discrepancy = False
        delta = 0.0
        msg: Optional[str] = None

        if target is not None:
            delta = total_eff - target
            if abs(delta) > 1e-4:
                has_discrepancy = True
                if delta > 0:
                    msg = (
                        f"Allocated marks ({total_eff:g}) exceed maximum marks "
                        f"({target:g}) by {delta:g} mark(s)."
                    )
                else:
                    msg = (
                        f"Allocated marks ({total_eff:g}) are less than maximum marks "
                        f"({target:g}) by {abs(delta):g} mark(s)."
                    )

        return PaperMarksReport(
            total_effective_marks=total_eff,
            total_available_marks=total_avail,
            max_marks_target=target,
            has_discrepancy=has_discrepancy,
            discrepancy_delta=delta,
            discrepancy_message=msg,
            section_reports=sec_reports,
        )
