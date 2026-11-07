"""Automated tests for Sub-Phase 6.1: Standalone Windows Packaging, Inno Setup Script & Self-Test CLI."""

from __future__ import annotations

from pathlib import Path

from scripts.build_windows import (
    APP_NAME,
    ENTRYPOINT,
    ISS_SCRIPT,
    build_pyinstaller_command,
    ensure_assets_ready,
    get_expected_executable_path,
    verify_executable,
)
from src.main import main, run_self_test


def test_cli_version_and_self_test_flags(capsys) -> None:
    """Verify `--version` and `--self-test` CLI flags execute headlessly and return 0."""
    rc_ver = main(["--version"])
    assert rc_ver == 0
    captured = capsys.readouterr()
    assert "Question Paper Studio" in captured.out
    assert "1.0.0" in captured.out

    rc_self = run_self_test()
    assert rc_self == 0


def test_pyinstaller_onedir_command_construction(tmp_path: Path) -> None:
    """Verify `build_pyinstaller_command` includes all required PyInstaller `--onedir` flags and data assets."""
    ensure_assets_ready()
    cmd = build_pyinstaller_command(clean=True, dist_dir=tmp_path / "dist", work_dir=tmp_path / "build")
    joined = " ".join(cmd)

    assert "--onedir" in cmd
    assert "--windowed" in cmd
    assert f"--name={APP_NAME}" in cmd
    assert "--collect-data=latex2mathml" in cmd
    assert "--collect-data=docx" in cmd
    assert "--hidden-import=PySide6.QtWebEngineWidgets" in cmd
    assert "--hidden-import=PySide6.QtPrintSupport" in cmd
    assert "assets" in joined
    assert str(ENTRYPOINT) in cmd

    expected_exe = get_expected_executable_path(tmp_path / "dist")
    assert expected_exe.parent.name == APP_NAME


def test_inno_setup_script_integrity() -> None:
    """Verify `scripts/installer.iss` exists and defines shortcuts, `.qpf` file associations, and output settings."""
    assert ISS_SCRIPT.exists()
    content = ISS_SCRIPT.read_text(encoding="utf-8")

    assert "[Setup]" in content
    assert "[Files]" in content
    assert "[Icons]" in content
    assert "[Registry]" in content
    assert "Setup_QuestionPaperStudio" in content
    assert "QuestionPaperStudio.exe" in content
    assert ".qpf" in content


def test_compiled_executable_verification() -> None:
    """Verify the built standalone executable in `dist/QuestionPaperStudio/` passes `--version` and `--self-test`."""
    exe_path = get_expected_executable_path()
    assert exe_path.exists(), f"Expected compiled executable at {exe_path}"
    assert verify_executable(exe_path) is True

