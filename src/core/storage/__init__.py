"""Storage and persistence managers: `.qpf` archive, template store, SQLite bank, and autosave."""

from src.core.storage.autosave_manager import (
    AutosaveManager,
    RecoveryCandidate,
)
from src.core.storage.qpf_archive import (
    ASSETS_ARCHIVE_PREFIX,
    MANIFEST_JSON_FILENAME,
    PROJECT_JSON_FILENAME,
    QPFArchive,
    QPFUnpackResult,
)
from src.core.storage.question_importer import (
    ImportErrorItem,
    QuestionImporter,
    QuestionImportReport,
)
from src.core.storage.sqlite_bank import (
    BankQuestionRecord,
    BankSearchFilter,
    LibraryAssetRecord,
    QuestionRevisionEntry,
    SQLiteQuestionBank,
)
from src.core.storage.template_store import (
    DEFAULT_TEMPLATES_DIR,
    TemplateImportReport,
    TemplateStore,
)

__all__ = [
    "ASSETS_ARCHIVE_PREFIX",
    "AutosaveManager",
    "BankQuestionRecord",
    "BankSearchFilter",
    "DEFAULT_TEMPLATES_DIR",
    "ImportErrorItem",
    "LibraryAssetRecord",
    "MANIFEST_JSON_FILENAME",
    "PROJECT_JSON_FILENAME",
    "QPFArchive",
    "QPFUnpackResult",
    "QuestionImportReport",
    "QuestionImporter",
    "QuestionRevisionEntry",
    "RecoveryCandidate",
    "SQLiteQuestionBank",
    "TemplateImportReport",
    "TemplateStore",
]
