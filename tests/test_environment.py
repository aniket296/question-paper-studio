"""Environment, dependency, and bundled asset verification tests for Sub-phase 0.2."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from scripts.generate_default_assets import (
    FONTS_DIR,
    FONT_REMOTE_URLS,
    ICONS_DIR,
    PROJECT_ROOT,
    SVG_ICONS,
    generate_all_assets,
    verify_font_header,
)


def test_python_version_minimum() -> None:
    """Verify Python runtime is 3.12 or newer."""
    assert sys.version_info >= (3, 12), f"Expected Python >= 3.12, got {sys.version}"


@pytest.mark.parametrize(
    "module_name",
    [
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "pydantic",
        "docx",
        "lxml",
        "lxml.etree",
        "latex2mathml.converter",
        "PIL",
        "pypdf",
        "pytestqt",
    ],
)
def test_core_package_imports(module_name: str) -> None:
    """Verify all required production and testing libraries import cleanly."""
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_bundled_fonts_present_and_valid() -> None:
    """Verify Noto Sans and Noto Sans Devanagari TTF files exist and have valid TrueType/OpenType headers."""
    generate_all_assets()
    for font_filename in FONT_REMOTE_URLS:
        font_path = FONTS_DIR / font_filename
        assert font_path.exists(), f"Missing bundled font: {font_path}"
        assert verify_font_header(font_path), f"Invalid TTF header in bundled font: {font_path}"


def test_bundled_icons_present_and_valid() -> None:
    """Verify all SVG UI icons and application icons (.png and .ico) exist and are non-empty."""
    generate_all_assets()
    for svg_name in SVG_ICONS:
        svg_path = ICONS_DIR / svg_name
        assert svg_path.exists(), f"Missing SVG icon: {svg_path}"
        content = svg_path.read_text(encoding="utf-8")
        assert "<svg" in content and "</svg>" in content

    for app_icon_name in ("app_icon.png", "app_icon.ico"):
        icon_path = ICONS_DIR / app_icon_name
        assert icon_path.exists(), f"Missing application icon: {icon_path}"
        assert icon_path.stat().st_size > 100


def test_project_configuration_and_readme() -> None:
    """Verify requirements.txt, pyproject.toml, and README.md exist and contain required specifications."""
    req_path = PROJECT_ROOT / "requirements.txt"
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    readme_path = PROJECT_ROOT / "README.md"

    assert req_path.exists()
    assert pyproject_path.exists()
    assert readme_path.exists()

    req_text = req_path.read_text(encoding="utf-8")
    for pkg in ("PySide6", "pydantic", "python-docx", "lxml", "latex2mathml", "Pillow", "pypdf", "pytest", "pytest-qt", "pyinstaller"):
        assert pkg in req_text

    readme_text = readme_path.read_text(encoding="utf-8")
    assert "Simple by Default, Powerful When Needed" in readme_text
    assert "Question Paper Studio" in readme_text
