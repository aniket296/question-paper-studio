"""SQLite3 + FTS5 Question Bank, Usage History, Revision History, and Reusable Asset Library."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from src.core.models.enums import BloomLevel, DifficultyLevel, QuestionType
from src.core.models.question_model import QuestionNode


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())


def _prompt_fingerprint(html: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", _strip_html(html)).lower().strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


@dataclass
class BankQuestionRecord:
    """Stored Question Bank record with revision and usage metadata."""

    bank_item_id: str
    question: QuestionNode
    plain_text: str
    subject: str
    unit: str
    chapter: str
    topic: str
    difficulty: str
    bloom_level: str
    tags: List[str]
    usage_count: int
    last_used_at: Optional[str]
    last_used_exam: Optional[str]
    current_version: int
    created_at: str
    updated_at: str


@dataclass
class QuestionRevisionEntry:
    """Historical snapshot of a question stored in `question_revisions`."""

    revision_id: int
    bank_item_id: str
    version_number: int
    question: QuestionNode
    change_note: str
    created_at: str


@dataclass
class LibraryAssetRecord:
    """Reusable image, diagram, equation, or logo stored in the Asset Library."""

    asset_id: str
    title: str
    asset_type: str  # "image", "diagram", "equation", "logo"
    file_path: str
    latex_source: str
    tags: List[str]
    sha256_hash: str
    created_at: str


@dataclass
class BankSearchFilter:
    """Search and filter parameters for querying the SQLite Question Bank."""

    query_text: str = ""
    question_type: Optional[QuestionType] = None
    subject: Optional[str] = None
    unit: Optional[str] = None
    chapter: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    bloom_level: Optional[BloomLevel] = None
    tags: List[str] = field(default_factory=list)
    min_marks: Optional[float] = None
    max_marks: Optional[float] = None
    exclude_used_since_iso: Optional[str] = None
    limit: int = 200


class SQLiteQuestionBank:
    """Offline SQLite3 + FTS5 Question Bank, Revision Manager, and Reusable Asset Library."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS question_bank (
                    bank_item_id TEXT PRIMARY KEY,
                    question_json TEXT NOT NULL,
                    plain_text TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    marks REAL,
                    subject TEXT DEFAULT '',
                    unit TEXT DEFAULT '',
                    chapter TEXT DEFAULT '',
                    topic TEXT DEFAULT '',
                    difficulty TEXT DEFAULT '',
                    bloom_level TEXT DEFAULT '',
                    tags_json TEXT DEFAULT '[]',
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    last_used_exam TEXT,
                    current_version INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_qb_fingerprint ON question_bank(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_qb_subject_topic ON question_bank(subject, topic);
                CREATE INDEX IF NOT EXISTS idx_qb_type ON question_bank(question_type);

                CREATE VIRTUAL TABLE IF NOT EXISTS question_bank_fts USING fts5(
                    bank_item_id UNINDEXED,
                    plain_text,
                    subject,
                    unit,
                    chapter,
                    topic,
                    tags_text
                );

                CREATE TABLE IF NOT EXISTS question_revisions (
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_item_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    question_json TEXT NOT NULL,
                    change_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (bank_item_id) REFERENCES question_bank(bank_item_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS question_usage_log (
                    usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_item_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    exam_title TEXT NOT NULL,
                    used_at TEXT NOT NULL,
                    FOREIGN KEY (bank_item_id) REFERENCES question_bank(bank_item_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS asset_library (
                    asset_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    file_path TEXT DEFAULT '',
                    latex_source TEXT DEFAULT '',
                    tags_json TEXT DEFAULT '[]',
                    sha256_hash TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _extract_taxonomy_fields(question: QuestionNode) -> Tuple[str, str, str, str, str, str, List[str]]:
        meta = question.taxonomy_metadata
        if meta is None:
            return ("", "", "", "", "", "", [])
        return (
            meta.subject or "",
            meta.unit or "",
            meta.chapter or "",
            meta.topic or "",
            meta.difficulty.value if meta.difficulty else "",
            meta.bloom_level.value if meta.bloom_level else "",
            list(meta.tags or []),
        )

    def add_question(
        self,
        question: QuestionNode,
        bank_item_id: Optional[str] = None,
        change_note: str = "Initial version",
    ) -> str:
        """Save a QuestionNode to the Question Bank, index in FTS5, and record revision 1."""
        item_id = bank_item_id or str(uuid4())
        snapshot = question.model_copy(deep=True)
        q_json = snapshot.model_dump_json()
        plain = _strip_html(snapshot.prompt_html)
        fp = _prompt_fingerprint(snapshot.prompt_html)
        subj, unit, chap, topic, diff, bloom, tags = self._extract_taxonomy_fields(snapshot)
        now = _utc_iso()

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO question_bank (
                    bank_item_id, question_json, plain_text, fingerprint, question_type,
                    marks, subject, unit, chapter, topic, difficulty, bloom_level,
                    tags_json, usage_count, last_used_at, last_used_exam,
                    current_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, 1, ?, ?)
                """,
                (
                    item_id,
                    q_json,
                    plain,
                    fp,
                    snapshot.question_type.value,
                    snapshot.marks,
                    subj,
                    unit,
                    chap,
                    topic,
                    diff,
                    bloom,
                    json.dumps(tags),
                    now,
                    now,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO question_bank_fts (
                    bank_item_id, plain_text, subject, unit, chapter, topic, tags_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, plain, subj, unit, chap, topic, " ".join(tags)),
            )
            self._conn.execute(
                """
                INSERT INTO question_revisions (
                    bank_item_id, version_number, question_json, change_note, created_at
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (item_id, q_json, change_note, now),
            )
        return item_id

    def update_question(
        self,
        bank_item_id: str,
        updated_question: QuestionNode,
        change_note: str = "Updated question",
    ) -> int:
        """Update a Question Bank item, increment its version, and store a new revision entry."""
        row = self._conn.execute(
            "SELECT current_version FROM question_bank WHERE bank_item_id = ?",
            (bank_item_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Bank item '{bank_item_id}' not found.")

        new_ver = int(row["current_version"]) + 1
        snapshot = updated_question.model_copy(deep=True)
        q_json = snapshot.model_dump_json()
        plain = _strip_html(snapshot.prompt_html)
        fp = _prompt_fingerprint(snapshot.prompt_html)
        subj, unit, chap, topic, diff, bloom, tags = self._extract_taxonomy_fields(snapshot)
        now = _utc_iso()

        with self._conn:
            self._conn.execute(
                """
                UPDATE question_bank SET
                    question_json = ?, plain_text = ?, fingerprint = ?, question_type = ?,
                    marks = ?, subject = ?, unit = ?, chapter = ?, topic = ?,
                    difficulty = ?, bloom_level = ?, tags_json = ?,
                    current_version = ?, updated_at = ?
                WHERE bank_item_id = ?
                """,
                (
                    q_json,
                    plain,
                    fp,
                    snapshot.question_type.value,
                    snapshot.marks,
                    subj,
                    unit,
                    chap,
                    topic,
                    diff,
                    bloom,
                    json.dumps(tags),
                    new_ver,
                    now,
                    bank_item_id,
                ),
            )
            self._conn.execute(
                "DELETE FROM question_bank_fts WHERE bank_item_id = ?",
                (bank_item_id,),
            )
            self._conn.execute(
                """
                INSERT INTO question_bank_fts (
                    bank_item_id, plain_text, subject, unit, chapter, topic, tags_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (bank_item_id, plain, subj, unit, chap, topic, " ".join(tags)),
            )
            self._conn.execute(
                """
                INSERT INTO question_revisions (
                    bank_item_id, version_number, question_json, change_note, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (bank_item_id, new_ver, q_json, change_note, now),
            )
        return new_ver

    def get_record(self, bank_item_id: str) -> Optional[BankQuestionRecord]:
        """Fetch a `BankQuestionRecord` by ID."""
        row = self._conn.execute(
            "SELECT * FROM question_bank WHERE bank_item_id = ?",
            (bank_item_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def create_question_snapshot_for_paper(self, bank_item_id: str) -> QuestionNode:
        """Return an independent deep-cloned QuestionNode with new UUIDs for insertion into a paper.

        Modifying or deleting the Question Bank item later will never mutate the paper's question.
        """
        rec = self.get_record(bank_item_id)
        if rec is None:
            raise KeyError(f"Bank item '{bank_item_id}' not found.")
        return rec.question.clone_with_new_ids()

    def delete_questions(self, bank_item_ids: List[str]) -> int:
        """Delete one or more questions from the Question Bank."""
        if not bank_item_ids:
            return 0
        placeholders = ",".join("?" for _ in bank_item_ids)
        with self._conn:
            cur = self._conn.execute(
                f"DELETE FROM question_bank WHERE bank_item_id IN ({placeholders})",
                tuple(bank_item_ids),
            )
            self._conn.execute(
                f"DELETE FROM question_bank_fts WHERE bank_item_id IN ({placeholders})",
                tuple(bank_item_ids),
            )
            return cur.rowcount

    def search(self, filters: Optional[BankSearchFilter] = None) -> List[BankQuestionRecord]:
        """Search and filter the Question Bank using FTS5 and structured SQL predicates."""
        f = filters or BankSearchFilter()
        sql = "SELECT qb.* FROM question_bank qb"
        params: List[object] = []
        where_clauses: List[str] = []

        if f.query_text.strip():
            # Sanitize FTS5 query tokens into prefix matches
            tokens = [re.sub(r"[^\w]", "", tok) for tok in f.query_text.split()]
            tokens = [f'"{tok}"*' for tok in tokens if tok]
            if tokens:
                fts_expr = " AND ".join(tokens)
                sql += " JOIN question_bank_fts fts ON qb.bank_item_id = fts.bank_item_id"
                where_clauses.append("question_bank_fts MATCH ?")
                params.append(fts_expr)

        if f.question_type is not None:
            where_clauses.append("qb.question_type = ?")
            params.append(f.question_type.value)
        if f.subject:
            where_clauses.append("LOWER(qb.subject) = LOWER(?)")
            params.append(f.subject.strip())
        if f.unit:
            where_clauses.append("LOWER(qb.unit) = LOWER(?)")
            params.append(f.unit.strip())
        if f.chapter:
            where_clauses.append("LOWER(qb.chapter) = LOWER(?)")
            params.append(f.chapter.strip())
        if f.topic:
            where_clauses.append("LOWER(qb.topic) = LOWER(?)")
            params.append(f.topic.strip())
        if f.difficulty is not None:
            where_clauses.append("qb.difficulty = ?")
            params.append(f.difficulty.value)
        if f.bloom_level is not None:
            where_clauses.append("qb.bloom_level = ?")
            params.append(f.bloom_level.value)
        if f.min_marks is not None:
            where_clauses.append("qb.marks >= ?")
            params.append(f.min_marks)
        if f.max_marks is not None:
            where_clauses.append("qb.marks <= ?")
            params.append(f.max_marks)
        if f.exclude_used_since_iso:
            where_clauses.append("(qb.last_used_at IS NULL OR qb.last_used_at < ?)")
            params.append(f.exclude_used_since_iso)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        sql += " ORDER BY qb.updated_at DESC LIMIT ?"
        params.append(f.limit)

        rows = self._conn.execute(sql, tuple(params)).fetchall()
        records = [self._row_to_record(r) for r in rows]

        if f.tags:
            req_tags = {t.lower().strip() for t in f.tags if t.strip()}
            records = [
                rec
                for rec in records
                if req_tags.issubset({t.lower() for t in rec.tags})
            ]
        return records

    def find_duplicates(self, prompt_html: str) -> List[BankQuestionRecord]:
        """Find existing bank questions with an identical normalized prompt fingerprint."""
        fp = _prompt_fingerprint(prompt_html)
        rows = self._conn.execute(
            "SELECT * FROM question_bank WHERE fingerprint = ?",
            (fp,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def record_usage(
        self,
        bank_item_id: str,
        project_id: str,
        exam_title: str,
    ) -> None:
        """Record that a bank question was used in an exam paper."""
        now = _utc_iso()
        with self._conn:
            self._conn.execute(
                """
                UPDATE question_bank SET
                    usage_count = usage_count + 1,
                    last_used_at = ?,
                    last_used_exam = ?
                WHERE bank_item_id = ?
                """,
                (now, exam_title, bank_item_id),
            )
            self._conn.execute(
                """
                INSERT INTO question_usage_log (bank_item_id, project_id, exam_title, used_at)
                VALUES (?, ?, ?, ?)
                """,
                (bank_item_id, project_id, exam_title, now),
            )

    def get_revision_history(self, bank_item_id: str) -> List[QuestionRevisionEntry]:
        """Return all revisions for `bank_item_id` ordered from oldest to newest."""
        rows = self._conn.execute(
            """
            SELECT * FROM question_revisions
            WHERE bank_item_id = ?
            ORDER BY version_number ASC
            """,
            (bank_item_id,),
        ).fetchall()
        return [
            QuestionRevisionEntry(
                revision_id=int(r["revision_id"]),
                bank_item_id=str(r["bank_item_id"]),
                version_number=int(r["version_number"]),
                question=QuestionNode.model_validate_json(r["question_json"]),
                change_note=str(r["change_note"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    def restore_revision(self, bank_item_id: str, version_number: int) -> BankQuestionRecord:
        """Restore a previous version of a question as the active state and record the restoration."""
        row = self._conn.execute(
            """
            SELECT question_json FROM question_revisions
            WHERE bank_item_id = ? AND version_number = ?
            """,
            (bank_item_id, version_number),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"Revision v{version_number} not found for bank item '{bank_item_id}'."
            )
        restored_q = QuestionNode.model_validate_json(row["question_json"])
        self.update_question(
            bank_item_id,
            restored_q,
            change_note=f"Restored from version {version_number}",
        )
        rec = self.get_record(bank_item_id)
        assert rec is not None
        return rec

    # ========================================================================
    # Reusable Asset Library (Images, Diagrams, Equations, Logos)
    # ========================================================================

    def add_library_asset(
        self,
        title: str,
        asset_type: str,
        file_path: str = "",
        latex_source: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a reusable diagram, logo, or LaTeX equation in the Asset Library."""
        asset_id = str(uuid4())
        tag_list = list(tags or [])
        digest = hashlib.sha256(f"{file_path}:{latex_source}".encode("utf-8")).hexdigest()[:16]
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO asset_library (
                    asset_id, title, asset_type, file_path, latex_source,
                    tags_json, sha256_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    title,
                    asset_type,
                    file_path,
                    latex_source,
                    json.dumps(tag_list),
                    digest,
                    _utc_iso(),
                ),
            )
        return asset_id

    def list_library_assets(self, asset_type: Optional[str] = None) -> List[LibraryAssetRecord]:
        """List reusable assets stored in the Asset Library."""
        if asset_type:
            rows = self._conn.execute(
                "SELECT * FROM asset_library WHERE asset_type = ? ORDER BY created_at DESC",
                (asset_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM asset_library ORDER BY created_at DESC"
            ).fetchall()

        return [
            LibraryAssetRecord(
                asset_id=str(r["asset_id"]),
                title=str(r["title"]),
                asset_type=str(r["asset_type"]),
                file_path=str(r["file_path"]),
                latex_source=str(r["latex_source"]),
                tags=json.loads(r["tags_json"] or "[]"),
                sha256_hash=str(r["sha256_hash"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> BankQuestionRecord:
        return BankQuestionRecord(
            bank_item_id=str(row["bank_item_id"]),
            question=QuestionNode.model_validate_json(row["question_json"]),
            plain_text=str(row["plain_text"]),
            subject=str(row["subject"]),
            unit=str(row["unit"]),
            chapter=str(row["chapter"]),
            topic=str(row["topic"]),
            difficulty=str(row["difficulty"]),
            bloom_level=str(row["bloom_level"]),
            tags=json.loads(row["tags_json"] or "[]"),
            usage_count=int(row["usage_count"]),
            last_used_at=row["last_used_at"],
            last_used_exam=row["last_used_exam"],
            current_version=int(row["current_version"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
