"""Bulk Question Importer from `.docx`, `.txt`, `.csv`, and `.tsv` with review & error reporting."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import docx

from src.core.models.enums import DifficultyLevel, FillBlankMode, QuestionType
from src.core.models.question_model import (
    BlankItem,
    FillBlankData,
    MCQData,
    MCQOption,
    MarkingScheme,
    QuestionNode,
    TaxonomyMetadata,
)


@dataclass
class ImportErrorItem:
    """Line or row-level error encountered while importing questions."""

    line_or_row: int
    raw_content: str
    reason: str


@dataclass
class QuestionImportReport:
    """Result of parsing questions from a file or text block."""

    source_name: str
    questions: List[QuestionNode] = field(default_factory=list)
    errors: List[ImportErrorItem] = field(default_factory=list)
    total_parsed: int = 0
    total_skipped: int = 0


_QUESTION_HEADER_RE = re.compile(
    r"^\s*(?:Q(?:uestion)?\s*\d+|\d+)[\.\)\:\-]\s+(?P<text>.+)$",
    re.IGNORECASE,
)
_MARKS_SUFFIX_RE = re.compile(
    r"[\[\(]\s*(?P<marks>\d+(?:\.\d+)?)\s*(?:marks?|m|pts?)?\s*[\]\)]\s*$",
    re.IGNORECASE,
)
_OPTION_LINE_RE = re.compile(
    r"^\s*(?P<star>\*)?\s*(?:[\(\[]?(?P<label>[A-Ha-h])[\)\]\.\:\-])\s+(?P<text>.+)$"
)
_ANSWER_LINE_RE = re.compile(
    r"^\s*(?:Ans(?:wer)?|Key|Correct)\s*[\:\=\-]\s*(?P<ans>.+)$",
    re.IGNORECASE,
)


class QuestionImporter:
    """Parses structured and semi-structured questions from `.txt`, `.docx`, `.csv`, and `.tsv`."""

    @staticmethod
    def import_file(file_path: Path | str) -> QuestionImportReport:
        """Import questions from a `.txt`, `.docx`, `.csv`, or `.tsv` file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Import file not found: '{path}'")

        ext = path.suffix.lower()
        if ext == ".txt":
            text = path.read_text(encoding="utf-8")
            return QuestionImporter.import_from_text(text, source_name=path.name)
        if ext == ".docx":
            return QuestionImporter.import_from_docx(path)
        if ext == ".csv":
            return QuestionImporter.import_from_delimited(path, delimiter=",")
        if ext == ".tsv":
            return QuestionImporter.import_from_delimited(path, delimiter="\t")

        raise ValueError(f"Unsupported question import file extension: '{ext}'")

    @staticmethod
    def _extract_marks_from_prompt(prompt: str) -> Tuple[str, Optional[float]]:
        """Extract trailing `[5 Marks]` or `(2M)` from a prompt line if present."""
        match = _MARKS_SUFFIX_RE.search(prompt)
        if not match:
            return prompt.strip(), None
        marks_val = float(match.group("marks"))
        cleaned = prompt[: match.start()].strip()
        return cleaned, marks_val

    @staticmethod
    def import_from_text(
        raw_text: str,
        source_name: str = "Text Input",
    ) -> QuestionImportReport:
        """Parse numbered questions, MCQ options (`A) ...`), and `Answer: X` lines from plain text."""
        report = QuestionImportReport(source_name=source_name)
        lines = raw_text.splitlines()

        current_prompt_lines: List[str] = []
        current_options: List[Tuple[str, str, bool]] = []  # (label, text, is_correct)
        current_answer_str: Optional[str] = None
        current_start_line: int = 1

        def _flush_block() -> None:
            nonlocal current_prompt_lines, current_options, current_answer_str
            if not current_prompt_lines and not current_options:
                return

            full_prompt = " ".join(current_prompt_lines).strip()
            if not full_prompt:
                report.errors.append(
                    ImportErrorItem(
                        line_or_row=current_start_line,
                        raw_content=str(current_options),
                        reason="Options found without a preceding question prompt.",
                    )
                )
                current_prompt_lines = []
                current_options = []
                current_answer_str = None
                return

            clean_prompt, marks = QuestionImporter._extract_marks_from_prompt(full_prompt)
            if not clean_prompt:
                report.errors.append(
                    ImportErrorItem(
                        line_or_row=current_start_line,
                        raw_content=full_prompt,
                        reason="Question prompt is empty after removing marks tag.",
                    )
                )
                current_prompt_lines = []
                current_options = []
                current_answer_str = None
                return

            if current_options:
                if len(current_options) < 2:
                    report.errors.append(
                        ImportErrorItem(
                            line_or_row=current_start_line,
                            raw_content=full_prompt,
                            reason="MCQ question has fewer than 2 options.",
                        )
                    )
                    current_prompt_lines = []
                    current_options = []
                    current_answer_str = None
                    return

                ans_token = (current_answer_str or "").strip().upper()
                mcq_opts: List[MCQOption] = []
                for lbl, opt_text, starred in current_options:
                    is_corr = starred or (ans_token == lbl.upper()) or (ans_token == opt_text.upper())
                    mcq_opts.append(
                        MCQOption(
                            text_html=opt_text,
                            is_correct=is_corr,
                            label=lbl.upper(),
                        )
                    )
                node = QuestionNode(
                    question_type=QuestionType.MCQ,
                    prompt_html=f"<p>{clean_prompt}</p>",
                    marks=marks if marks is not None else 1.0,
                    type_data=MCQData(options=mcq_opts),
                )
            elif "___" in clean_prompt:
                node = QuestionNode(
                    question_type=QuestionType.FILL_IN_THE_BLANK,
                    prompt_html=f"<p>{clean_prompt}</p>",
                    marks=marks if marks is not None else 1.0,
                    type_data=FillBlankData(
                        mode=FillBlankMode.WITHOUT_OPTIONS,
                        blanks=[BlankItem(blank_index=1, correct_answer=current_answer_str or "")],
                    ),
                )
            else:
                scheme = (
                    MarkingScheme(model_answer_html=f"<p>{current_answer_str}</p>")
                    if current_answer_str
                    else None
                )
                node = QuestionNode(
                    question_type=QuestionType.NORMAL,
                    prompt_html=f"<p>{clean_prompt}</p>",
                    marks=marks if marks is not None else 2.0,
                    marking_scheme=scheme,
                )

            report.questions.append(node)
            current_prompt_lines = []
            current_options = []
            current_answer_str = None

        for line_no, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped:
                _flush_block()
                continue

            q_match = _QUESTION_HEADER_RE.match(stripped)
            if q_match:
                _flush_block()
                current_start_line = line_no
                current_prompt_lines.append(q_match.group("text").strip())
                continue

            opt_match = _OPTION_LINE_RE.match(stripped)
            if opt_match:
                starred = bool(opt_match.group("star"))
                lbl = opt_match.group("label").upper()
                opt_txt = opt_match.group("text").strip()
                if opt_txt.endswith("*"):
                    starred = True
                    opt_txt = opt_txt[:-1].strip()
                current_options.append((lbl, opt_txt, starred))
                continue

            ans_match = _ANSWER_LINE_RE.match(stripped)
            if ans_match:
                current_answer_str = ans_match.group("ans").strip()
                continue

            # Continuation line or unnumbered question line
            if not current_prompt_lines:
                current_start_line = line_no
            current_prompt_lines.append(stripped)

        _flush_block()
        report.total_parsed = len(report.questions)
        report.total_skipped = len(report.errors)
        return report

    @staticmethod
    def import_from_docx(docx_path: Path | str) -> QuestionImportReport:
        """Extract paragraphs from a Word `.docx` file and parse questions."""
        doc = docx.Document(str(docx_path))
        paragraphs = [p.text for p in doc.paragraphs]
        joined = "\n".join(paragraphs)
        return QuestionImporter.import_from_text(joined, source_name=Path(docx_path).name)

    @staticmethod
    def import_from_delimited(
        file_path: Path | str,
        delimiter: str = ",",
    ) -> QuestionImportReport:
        """Import structured questions from CSV or TSV files.

        Supported columns (case-insensitive):
        `question` / `prompt`, `type` / `question_type`, `marks`,
        `option_a`, `option_b`, `option_c`, `option_d`, `answer` / `correct_answer`,
        `subject`, `topic`, `difficulty`, `tags`
        """
        path = Path(file_path)
        report = QuestionImportReport(source_name=path.name)

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row_idx, row in enumerate(reader, start=2):
                norm_row = {
                    (k or "").strip().lower(): (v or "").strip()
                    for k, v in row.items()
                }
                prompt = norm_row.get("question") or norm_row.get("prompt") or ""
                if not prompt:
                    report.errors.append(
                        ImportErrorItem(
                            line_or_row=row_idx,
                            raw_content=str(row),
                            reason="Missing 'question' or 'prompt' column value.",
                        )
                    )
                    continue

                raw_type = (
                    norm_row.get("type")
                    or norm_row.get("question_type")
                    or "NORMAL"
                ).upper()

                try:
                    qtype = QuestionType(raw_type)
                except ValueError:
                    # Handle common aliases
                    if raw_type in ("BLANK", "FIB", "FILL_BLANK"):
                        qtype = QuestionType.FILL_IN_THE_BLANK
                    elif raw_type in ("MATCH", "MATCH_PAIR"):
                        qtype = QuestionType.MATCH_THE_PAIR
                    else:
                        qtype = QuestionType.NORMAL

                marks_str = norm_row.get("marks")
                marks_val: Optional[float] = None
                if marks_str:
                    try:
                        marks_val = float(marks_str)
                    except ValueError:
                        report.errors.append(
                            ImportErrorItem(
                                line_or_row=row_idx,
                                raw_content=marks_str,
                                reason=f"Invalid numeric marks value '{marks_str}'.",
                            )
                        )
                        continue

                ans_val = norm_row.get("answer") or norm_row.get("correct_answer") or ""

                # Taxonomy metadata if present
                subj = norm_row.get("subject") or None
                topic = norm_row.get("topic") or None
                diff_str = norm_row.get("difficulty") or ""
                diff_enum: Optional[DifficultyLevel] = None
                for d in DifficultyLevel:
                    if d.value.lower() == diff_str.lower():
                        diff_enum = d
                        break
                tags_raw = norm_row.get("tags") or ""
                tags_list = [t.strip() for t in tags_raw.split(";") if t.strip()] if tags_raw else []

                taxonomy = (
                    TaxonomyMetadata(
                        subject=subj,
                        topic=topic,
                        difficulty=diff_enum,
                        tags=tags_list,
                    )
                    if any([subj, topic, diff_enum, tags_list])
                    else None
                )

                # Construct question node by type
                opt_texts = [
                    norm_row.get("option_a", ""),
                    norm_row.get("option_b", ""),
                    norm_row.get("option_c", ""),
                    norm_row.get("option_d", ""),
                ]
                non_empty_opts = [(chr(ord("A") + i), txt) for i, txt in enumerate(opt_texts) if txt]

                if qtype == QuestionType.MCQ or len(non_empty_opts) >= 2:
                    if len(non_empty_opts) < 2:
                        report.errors.append(
                            ImportErrorItem(
                                line_or_row=row_idx,
                                raw_content=prompt,
                                reason="MCQ row requires at least 2 option columns (option_a, option_b).",
                            )
                        )
                        continue
                    ans_upper = ans_val.upper().strip()
                    mcq_options = [
                        MCQOption(
                            label=lbl,
                            text_html=txt,
                            is_correct=(ans_upper == lbl or ans_upper == txt.upper()),
                        )
                        for lbl, txt in non_empty_opts
                    ]
                    node = QuestionNode(
                        question_type=QuestionType.MCQ,
                        prompt_html=f"<p>{prompt}</p>",
                        marks=marks_val if marks_val is not None else 1.0,
                        type_data=MCQData(options=mcq_options),
                        taxonomy_metadata=taxonomy,
                    )
                elif qtype == QuestionType.FILL_IN_THE_BLANK:
                    node = QuestionNode(
                        question_type=QuestionType.FILL_IN_THE_BLANK,
                        prompt_html=f"<p>{prompt}</p>",
                        marks=marks_val if marks_val is not None else 1.0,
                        type_data=FillBlankData(
                            mode=FillBlankMode.WITHOUT_OPTIONS,
                            blanks=[BlankItem(blank_index=1, correct_answer=ans_val)],
                        ),
                        taxonomy_metadata=taxonomy,
                    )
                else:
                    scheme = (
                        MarkingScheme(model_answer_html=f"<p>{ans_val}</p>")
                        if ans_val
                        else None
                    )
                    node = QuestionNode(
                        question_type=qtype,
                        prompt_html=f"<p>{prompt}</p>",
                        marks=marks_val if marks_val is not None else 2.0,
                        marking_scheme=scheme,
                        taxonomy_metadata=taxonomy,
                    )

                report.questions.append(node)

        report.total_parsed = len(report.questions)
        report.total_skipped = len(report.errors)
        return report
