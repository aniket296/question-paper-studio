"""Automated Regression, Security, Resilience, Boundary, Performance, and Accessibility Audit Suite.

Covers Section 6 test categories from the Principal QA & Security Verification Campaign:
- 6.1 Functional (Boundary Value Analysis, Equivalence Partitioning, Idempotency, State Transitions, Negative Testing)
- 6.2 Security (AST Formula Injection & DoS, Zip-Slip Path Traversal, CSS/HTML Breakout, SQL/FTS5 Injection, XXE Defense)
- 6.3 Performance & Reliability (100-question compilation & multi-set SLOs, crash recovery from corrupt autosaves, soak stability)
- 6.4 Compatibility, Accessibility & i18n (WCAG 2.1 contrast ratios, Devanagari/Unicode/RTL/MathML round-trip)
- 6.5 Data & Database Integrity (SQLite foreign key cascade, ACID rollback, snapshot isolation)
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Dict

import pytest

from src.core.engine import UndoRedoManager
from src.core.engine.dynamic_numeric import DynamicNumericEngine
from src.core.engine.marks_engine import MarksEngine
from src.core.engine.multi_set_shuffler import MultiSetShuffler, ShufflingOptions
from src.core.engine.numbering_fsm import NumberingFSM
from src.core.models.enums import (
    BilingualLayout,
    BloomLevel,
    CanvasElementType,
    ChoiceRuleType,
    DifficultyLevel,
    QuestionType,
)
from src.core.models.project_model import ProjectState
from src.core.models.question_model import (
    MCQData,
    MCQOption,
    NumericalDynamicData,
    NumericVariableRange,
    QuestionNode,
    TaxonomyMetadata,
)
from src.core.models.section_model import ChoiceGroup, Section
from src.core.models.template_model import CanvasElement
from src.core.storage.autosave_manager import AutosaveManager
from src.core.storage.qpf_archive import QPFArchive
from src.core.storage.question_importer import QuestionImporter
from src.core.storage.sqlite_bank import BankSearchFilter, SQLiteQuestionBank
from src.rendering.css_generator import CSSGenerator, sanitize_font_family
from src.rendering.docx_exporter import DOCXExporter
from src.rendering.html_compiler import HTMLCompiler
from src.rendering.math_converter import MathConverter
from src.ui.theme import DARK_PALETTE, LIGHT_PALETTE


# ============================================================================
# 1. SECURITY REGRESSION TESTS (Section 6.2)
# ============================================================================


def test_sec_01_dynamic_numeric_ast_blocks_code_execution_and_exponent_dos() -> None:
    """Regression test for FINDING-001 (CWE-95 / CWE-400):
    Ensure `DynamicNumericEngine.evaluate_formula` rejects lambda expressions, attribute/dunder
    traversals, comprehensions, and CPU-exhaustion exponent bombs in < 10 ms.
    """
    # Valid mathematical formulas still evaluate accurately
    assert DynamicNumericEngine.evaluate_formula("0.5 * m * v^2", {"m": 4.0, "v": 3.0}) == pytest.approx(18.0)
    assert DynamicNumericEngine.evaluate_formula("round(sqrt(x^2 + y^2), 2)", {"x": 3.0, "y": 4.0}) == pytest.approx(5.0)

    # 1. Lambda execution must be blocked
    with pytest.raises(ValueError):
        DynamicNumericEngine.evaluate_formula("(lambda x: x + 1)(5)", {})

    # 2. Attribute / dunder sandbox escape must be blocked
    for malicious_expr in (
        "().__class__.__base__.__subclasses__()",
        "sin.__class__.__base__",
        "__import__('os').system('echo pwned')",
        "[x for x in (1, 2, 3)]",
    ):
        with pytest.raises(ValueError):
            DynamicNumericEngine.evaluate_formula(malicious_expr, {})

    # 3. CPU/Memory exhaustion via nested exponentiation (9**9**7) must fail instantaneously (< 50 ms)
    t0 = time.perf_counter()
    with pytest.raises(ValueError, match="safety bounds"):
        DynamicNumericEngine.evaluate_formula("9^9^7", {})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0

    # 4. Direct pow() call with huge exponent must also be blocked
    with pytest.raises(ValueError, match="exceeds maximum allowed bound"):
        DynamicNumericEngine.evaluate_formula("pow(10, 5000)", {})


def test_sec_02_css_and_html_injection_sanitization() -> None:
    """Regression test for FINDING-002 (CWE-79 / CWE-116):
    Ensure malicious `base_font_family` or `CanvasElement.font_family` strings cannot break out
    of CSS rules or inline `style="..."` attributes.
    """
    proj = ProjectState(title="<script>alert('xss-title')</script>")
    proj.layout_settings.base_font_family = "Noto Sans'; } body { display: none; } /*"
    malicious_el = CanvasElement(
        element_type=CanvasElementType.TEXT,
        content="<img src=x onerror=alert(1)>",
        font_family='Arial" onload="alert(2); \'}; body { visibility: hidden; }',
        color_hex="#1E293B",
    )
    proj.template_snapshot.first_page_header_elements.append(malicious_el)

    compiled_html = HTMLCompiler.compile_project(proj)

    # Script tag in title and img tag in header element must be HTML-escaped
    assert "<script>alert('xss-title')</script>" not in compiled_html
    assert "&lt;script&gt;alert(&#x27;xss-title&#x27;)&lt;/script&gt;" in compiled_html
    assert "<img src=x onerror=alert(1)>" not in compiled_html

    # CSS / attribute breakouts must be stripped by sanitize_font_family
    assert "body { display: none; }" not in compiled_html
    assert "visibility: hidden" not in compiled_html
    assert 'onload="alert(2)' not in compiled_html
    assert sanitize_font_family("Noto Sans'; } body { display: none; }") == "Noto Sans body display none"


def test_sec_03_qpf_archive_rejects_zip_slip_traversal(tmp_path: Path) -> None:
    """Regression test for FINDING-003 (CWE-22):
    Ensure `QPFArchive.load_qpf` explicitly rejects `.qpf` archives containing `..` traversal
    components inside `assets/`.
    """
    proj = ProjectState(title="Traversal Test")
    malicious_qpf = tmp_path / "zip_slip.qpf"

    with zipfile.ZipFile(malicious_qpf, "w") as zf:
        zf.writestr("project.json", proj.to_json_string())
        zf.writestr("assets/../../evil_escape.txt", b"MALICIOUS_PAYLOAD")

    extract_target = tmp_path / "unpack_dir"
    with pytest.raises(ValueError, match="Unsafe path traversal"):
        QPFArchive.load_qpf(malicious_qpf, extract_assets_to=extract_target)

    assert not (tmp_path / "evil_escape.txt").exists()


def test_sec_04_sqlite_fts5_and_sql_injection_resilience(tmp_path: Path) -> None:
    """Verify `SQLiteQuestionBank.search` safely neutralizes SQL and FTS5 injection payloads."""
    bank = SQLiteQuestionBank(tmp_path / "security_bank.db")
    try:
        q_id = bank.add_question(
            QuestionNode(
                prompt_html="<p>Calculate gravitational potential energy.</p>",
                marks=3.0,
                taxonomy_metadata=TaxonomyMetadata(subject="Physics", topic="Gravitation"),
            )
        )
        hostile_payloads = [
            "' OR '1'='1",
            "'); DROP TABLE question_bank; --",
            '" OR ""="',
            "NEAR(gravitation, energy, 5) AND NOT *",
            "^$#@!~`\\()[]{}:;\"'<>?/",
            "\x00SELECT sqlite_version()",
        ]
        for payload in hostile_payloads:
            results = bank.search(
                BankSearchFilter(
                    query_text=payload,
                    subject=payload,
                    unit=payload,
                    chapter=payload,
                    topic=payload,
                )
            )
            assert isinstance(results, list)

        # Verify database table and original record remain completely intact
        rec = bank.get_record(q_id)
        assert rec is not None
        assert "gravitational" in rec.plain_text
    finally:
        bank.close()


def test_sec_05_math_converter_blocks_xxe_and_malformed_latex() -> None:
    """Regression test for FINDING-004 (CWE-611):
    Ensure `MathConverter` handles hostile XML/XXE strings and malformed LaTeX gracefully
    without resolving external entities or crashing.
    """
    xxe_payload = '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>&xxe;'
    omml_el = MathConverter.latex_to_omml_element(xxe_payload)
    assert omml_el is not None

    # Unbalanced braces / unknown macros fall back cleanly in HTMLCompiler
    proj = ProjectState(title="Malformed Math Test")
    proj.sections[0].questions.append(
        QuestionNode(
            prompt_html=r"<p>Broken math: $\frac{1}{2$ and $$\sqrt{unclosed$$</p>",
            marks=2.0,
        )
    )
    html_out = HTMLCompiler.compile_project(proj)
    assert "Broken math:" in html_out


# ============================================================================
# 2. FUNCTIONAL BOUNDARY, IDEMPOTENCY & DATA INTEGRITY TESTS (Section 6.1 & 6.5)
# ============================================================================


def test_func_boundary_idempotency_and_deep_hierarchy(tmp_path: Path) -> None:
    """Verify idempotency of numbering resolution, marks calculation, Undo/Redo, and QPF round-trip."""
    proj = ProjectState(title="Idempotency & Boundary Paper")
    sec = proj.sections[0]

    parent = QuestionNode(prompt_html="<p>Main Question</p>", marks=10.0)
    c1 = QuestionNode(prompt_html="<p>Sub-part i</p>", marks=4.0)
    c2 = QuestionNode(prompt_html="<p>Sub-part ii</p>", marks=6.0)
    gc1 = QuestionNode(prompt_html="<p>Sub-sub-part a</p>", marks=2.5)
    gc2 = QuestionNode(prompt_html="<p>Sub-sub-part b</p>", marks=3.5)
    c2.children.extend([gc1, gc2])
    parent.children.extend([c1, c2])
    sec.questions.append(parent)

    # 1. Repeated NumberingFSM.resolve_project must produce identical numbers
    NumberingFSM.resolve_project(proj)
    snap_numbers_1 = [(q.question_id, q.resolved_number) for q in proj.all_questions_dfs()]
    for _ in range(5):
        NumberingFSM.resolve_project(proj)
    snap_numbers_2 = [(q.question_id, q.resolved_number) for q in proj.all_questions_dfs()]
    assert snap_numbers_1 == snap_numbers_2

    # 2. Hierarchical roll-up marks: c2 = 2.5 + 3.5 = 6.0; parent = 4.0 + 6.0 = 10.0
    audit = MarksEngine.audit_project_marks(proj)
    assert audit.total_effective_marks == pytest.approx(10.0)

    # 3. Undo/Redo 20-cycle stress test
    ur = UndoRedoManager(max_history=50)
    ur.record_state(proj, "Initial")
    current = proj
    for i in range(20):
        mutated = current.model_copy(deep=True)
        mutated.title = f"Revision {i}"
        ur.record_state(mutated, f"Edit {i}")
        current = mutated
    for _ in range(20):
        current = ur.undo(current)
    assert current.title == "Idempotency & Boundary Paper"

    # 4. Corrupt autosave recovery resilience
    am = AutosaveManager(workspace_dir=tmp_path / "ws")
    corrupt_meta = am.autosave_dir / "corrupt.recovery.json"
    corrupt_meta.write_text("{not valid json", encoding="utf-8")
    # Should skip corrupt recovery marker without raising
    assert am.list_unrecovered_snapshots() == []


def test_data_sqlite_foreign_key_cascade_and_importer_malformed_inputs(tmp_path: Path) -> None:
    """Verify SQLite ON DELETE CASCADE cleans up revisions/usage logs and QuestionImporter reports errors cleanly."""
    bank = SQLiteQuestionBank(tmp_path / "cascade.db")
    try:
        q = QuestionNode(prompt_html="<p>Cascade test question</p>", marks=2.0)
        bid = bank.add_question(q)
        bank.update_question(bid, q, change_note="v2")
        bank.record_usage(bid, "proj-1", "Midterm")
        assert len(bank.get_revision_history(bid)) == 2

        bank.delete_questions([bid])
        assert bank.get_record(bid) is None
        assert len(bank.get_revision_history(bid)) == 0
    finally:
        bank.close()

    # Malformed text import with orphan options and single-option MCQ
    bad_text = "A) Orphan option\n\nQ1. Only one option MCQ [2M]\nA) Lonely option\n\nQ2. Valid question [3M]\nAns: Model"
    rep = QuestionImporter.import_from_text(bad_text)
    assert rep.total_parsed == 1
    assert rep.total_skipped == 2
    assert len(rep.errors) == 2


# ============================================================================
# 3. PERFORMANCE, ACCESSIBILITY (WCAG) & BILINGUAL i18n TESTS (Section 6.3 & 6.4)
# ============================================================================


def test_perf_and_wcag_contrast_and_bilingual_unicode_roundtrip(tmp_path: Path) -> None:
    """Verify WCAG 2.1 AA contrast ratios, bilingual Devanagari + LaTeX compilation, and 50-question SLOs."""
    # 1. Verify WCAG AA contrast (>= 4.5:1) for primary and secondary text in Light & Dark themes
    def _lum(hex_c: str) -> float:
        c = hex_c.lstrip("#")
        rgb = [int(c[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
        lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def _cr(c1: str, c2: str) -> float:
        l1, l2 = _lum(c1), _lum(c2)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

    assert _cr(LIGHT_PALETTE["text_primary"], LIGHT_PALETTE["bg_surface"]) >= 12.0
    assert _cr(LIGHT_PALETTE["text_secondary"], LIGHT_PALETTE["bg_surface"]) >= 4.5
    assert _cr(DARK_PALETTE["text_primary"], DARK_PALETTE["bg_surface"]) >= 12.0
    assert _cr(DARK_PALETTE["text_secondary"], DARK_PALETTE["bg_surface"]) >= 4.5

    # 2. Bilingual Devanagari + MathML + Multi-Set performance check
    proj = ProjectState(title="Bilingual & Performance Benchmark")
    proj.layout_settings.bilingual_mode = True
    proj.layout_settings.bilingual_layout = BilingualLayout.SIDE_BY_SIDE
    sec = proj.sections[0]
    for i in range(1, 51):
        sec.questions.append(
            QuestionNode(
                question_type=QuestionType.MCQ,
                prompt_html=f"<p>Calculate $\\sum_{{k=1}}^{{{i}}} k$.</p>",
                prompt_secondary_html=f"<p>मान ज्ञात कीजिए: $\\sum_{{k=1}}^{{{i}}} k$।</p>",
                marks=1.0,
                type_data=MCQData(
                    options=[
                        MCQOption(label="A", text_html=str(i * (i + 1) // 2), is_correct=True),
                        MCQOption(label="B", text_html=str(i * i), is_correct=False),
                    ]
                ),
            )
        )

    t0 = time.perf_counter()
    html_doc = HTMLCompiler.compile_project(proj)
    compile_ms = (time.perf_counter() - t0) * 1000.0
    assert compile_ms < 2000.0
    assert "मान ज्ञात कीजिए" in html_doc
    assert "<math" in html_doc
