"""Blueprint Validator Engine.

Compares actual paper metrics (topic, difficulty, Bloom taxonomy, question type)
against optional ExamBlueprint target distributions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.core.models.blueprint_model import ExamBlueprint
from src.core.models.enums import BloomLevel, DifficultyLevel, QuestionType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode


@dataclass
class DimensionVariance:
    """Variance analysis for a single category within a blueprint dimension."""

    category: str
    target_marks: float
    actual_marks: float
    variance_marks: float
    is_compliant: bool
    message: str


@dataclass
class BlueprintComplianceReport:
    """Complete validation report comparing paper against an ExamBlueprint."""

    blueprint_name: str
    target_total_marks: float
    actual_total_marks: float
    overall_compliant: bool
    topic_variances: List[DimensionVariance] = field(default_factory=list)
    question_type_variances: List[DimensionVariance] = field(default_factory=list)
    difficulty_variances: List[DimensionVariance] = field(default_factory=list)
    bloom_variances: List[DimensionVariance] = field(default_factory=list)
    summary_messages: List[str] = field(default_factory=list)


class BlueprintValidator:
    """Validates paper metrics against an optional ExamBlueprint."""

    @staticmethod
    def validate_project(
        project: ProjectState,
        blueprint: Optional[ExamBlueprint] = None,
        tolerance_marks: float = 0.5,
    ) -> BlueprintComplianceReport:
        """Compare `project` against its attached blueprint or `blueprint` parameter."""
        bp = blueprint or project.blueprint
        if bp is None:
            raise ValueError("No blueprint provided or attached to project.")

        all_nodes = project.all_questions_dfs()

        # Collect metrics from leaf questions or questions with marks
        actual_topic_marks: Dict[str, float] = {}
        actual_type_marks: Dict[str, float] = {}
        actual_diff_marks: Dict[str, float] = {}
        actual_bloom_marks: Dict[str, float] = {}
        actual_total = 0.0

        for node in all_nodes:
            # Only count leaf questions or questions without children to prevent double counting
            if node.children:
                continue

            marks = float(node.marks) if node.marks is not None else 0.0
            actual_total += marks

            # Question Type
            qtype_str = node.question_type.value
            actual_type_marks[qtype_str] = actual_type_marks.get(qtype_str, 0.0) + marks

            # Taxonomy metadata
            if node.taxonomy_metadata is not None:
                meta = node.taxonomy_metadata
                if meta.topic:
                    t_str = meta.topic.strip()
                    actual_topic_marks[t_str] = actual_topic_marks.get(t_str, 0.0) + marks
                if meta.difficulty:
                    d_str = meta.difficulty.value
                    actual_diff_marks[d_str] = actual_diff_marks.get(d_str, 0.0) + marks
                if meta.bloom_level:
                    b_str = meta.bloom_level.value
                    actual_bloom_marks[b_str] = actual_bloom_marks.get(b_str, 0.0) + marks

        def _compute_variances(
            targets: Dict[str, float],
            actuals: Dict[str, float],
        ) -> List[DimensionVariance]:
            results: List[DimensionVariance] = []
            if not targets:
                # If no targets were specified for this dimension, it is not enforced
                return results

            all_keys = set(targets.keys()) | set(actuals.keys())
            for key in sorted(all_keys):
                t_val = targets.get(key, 0.0)
                a_val = actuals.get(key, 0.0)
                diff = a_val - t_val
                compliant = abs(diff) <= tolerance_marks
                if compliant:
                    msg = f"{key}: Matched target ({a_val:g} / {t_val:g} marks)"
                elif diff > 0:
                    msg = f"{key}: Over target by +{diff:g} marks ({a_val:g} actual vs {t_val:g} target)"
                else:
                    msg = f"{key}: Under target by {diff:g} marks ({a_val:g} actual vs {t_val:g} target)"

                results.append(
                    DimensionVariance(
                        category=key,
                        target_marks=t_val,
                        actual_marks=a_val,
                        variance_marks=diff,
                        is_compliant=compliant,
                        message=msg,
                    )
                )
            return results

        topic_var = _compute_variances(bp.topic_marks_distribution, actual_topic_marks)
        type_var = _compute_variances(bp.question_type_marks_distribution, actual_type_marks)
        diff_var = _compute_variances(bp.difficulty_marks_distribution, actual_diff_marks)
        bloom_var = _compute_variances(bp.bloom_marks_distribution, actual_bloom_marks)

        total_compliant = abs(actual_total - bp.total_marks_target) <= tolerance_marks
        all_var_compliant = (
            all(v.is_compliant for v in topic_var)
            and all(v.is_compliant for v in type_var)
            and all(v.is_compliant for v in diff_var)
            and all(v.is_compliant for v in bloom_var)
        )
        overall = total_compliant and all_var_compliant

        summaries: List[str] = []
        if overall:
            summaries.append(f"Paper 100% compliant with blueprint '{bp.name}'.")
        else:
            if not total_compliant:
                summaries.append(
                    f"Total marks discrepancy: {actual_total:g} actual vs {bp.total_marks_target:g} target."
                )
            non_comp_topics = [v.category for v in topic_var if not v.is_compliant]
            if non_comp_topics:
                summaries.append(f"Topic mismatches: {', '.join(non_comp_topics)}")
            non_comp_diff = [v.category for v in diff_var if not v.is_compliant]
            if non_comp_diff:
                summaries.append(f"Difficulty mismatches: {', '.join(non_comp_diff)}")

        return BlueprintComplianceReport(
            blueprint_name=bp.name,
            target_total_marks=bp.total_marks_target,
            actual_total_marks=actual_total,
            overall_compliant=overall,
            topic_variances=topic_var,
            question_type_variances=type_var,
            difficulty_variances=diff_var,
            bloom_variances=bloom_var,
            summary_messages=summaries,
        )
