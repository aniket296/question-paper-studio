"""Advanced examination features: multi-set generation, question bank, blueprint, quality audit, and post-exam diagnostics."""

from src.ui.advanced.blueprint_dialog import BlueprintDialog, get_built_in_pattern_presets
from src.ui.advanced.multi_set_dialog import MultiSetDialog
from src.ui.advanced.post_exam_dialog import PostExamDialog
from src.ui.advanced.quality_check_panel import QualityCheckPanel
from src.ui.advanced.question_bank_drawer import QuestionBankDrawer, RevisionHistoryDialog

__all__ = [
    "BlueprintDialog",
    "get_built_in_pattern_presets",
    "MultiSetDialog",
    "PostExamDialog",
    "QualityCheckPanel",
    "QuestionBankDrawer",
    "RevisionHistoryDialog",
]

