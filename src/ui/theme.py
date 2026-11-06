"""Modern Desktop Theme, Color Tokens, Typography Registration, and Qt Stylesheet."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"

LIGHT_PALETTE: Dict[str, str] = {
    "bg_primary": "#F8FAFC",
    "bg_surface": "#FFFFFF",
    "bg_elevated": "#F1F5F9",
    "border": "#CBD5E1",
    "border_strong": "#94A3B8",
    "text_primary": "#0F172A",
    "text_secondary": "#475569",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#DBEAFE",
    "success": "#059669",
    "warning": "#D97706",
    "danger": "#DC2626",
}

DARK_PALETTE: Dict[str, str] = {
    "bg_primary": "#0F172A",
    "bg_surface": "#1E293B",
    "bg_elevated": "#334155",
    "border": "#475569",
    "border_strong": "#64748B",
    "text_primary": "#F8FAFC",
    "text_secondary": "#CBD5E1",
    "accent": "#3B82F6",
    "accent_hover": "#60A5FA",
    "accent_soft": "#1E3A8A",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
}


class ThemeManager:
    """Registers bundled Unicode fonts and applies the application QSS stylesheet."""

    @staticmethod
    def register_bundled_fonts() -> List[str]:
        """Load bundled Noto Sans and Noto Sans Devanagari `.ttf` files into `QFontDatabase`."""
        if QApplication.instance() is None:
            QApplication([])
        loaded_families: List[str] = []
        if not FONTS_DIR.exists():
            return loaded_families

        for ttf_file in sorted(FONTS_DIR.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(ttf_file))
            if font_id >= 0:
                fams = QFontDatabase.applicationFontFamilies(font_id)
                for f in fams:
                    if f not in loaded_families:
                        loaded_families.append(f)
        return loaded_families

    @staticmethod
    def build_stylesheet(dark_mode: bool = False) -> str:
        """Construct the complete Qt Style Sheet (QSS) for light or dark desktop theme."""
        p = DARK_PALETTE if dark_mode else LIGHT_PALETTE
        return f"""
QMainWindow, QDialog {{
    background-color: {p['bg_primary']};
    color: {p['text_primary']};
    font-family: 'Noto Sans', 'Segoe UI', sans-serif;
    font-size: 10pt;
}}

QWidget {{
    color: {p['text_primary']};
    font-family: 'Noto Sans', 'Noto Sans Devanagari', 'Segoe UI', sans-serif;
}}

QFrame#CardFrame, QFrame#TemplateCard {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
}}

QFrame#CardFrame:hover, QFrame#TemplateCard:hover {{
    border: 1px solid {p['accent']};
}}

QFrame#TemplateCardSelected {{
    background-color: {p['accent_soft']};
    border: 2px solid {p['accent']};
    border-radius: 8px;
}}

QPushButton {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['border_strong']};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    color: {p['text_primary']};
}}

QPushButton:hover {{
    background-color: {p['bg_elevated']};
    border-color: {p['accent']};
}}

QPushButton:disabled {{
    color: {p['border_strong']};
    background-color: {p['bg_elevated']};
}}

QPushButton#PrimaryButton {{
    background-color: {p['accent']};
    border: 1px solid {p['accent']};
    color: #FFFFFF;
    font-weight: 700;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {p['accent_hover']};
}}

QPushButton#DangerButton {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['danger']};
    color: {p['danger']};
}}

QPushButton#DangerButton:hover {{
    background-color: {p['danger']};
    color: #FFFFFF;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['border_strong']};
    border-radius: 5px;
    padding: 5px 8px;
    color: {p['text_primary']};
}}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {p['accent']};
}}

QTreeWidget, QListWidget, QTableWidget {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

QStatusBar {{
    background-color: {p['bg_surface']};
    border-top: 1px solid {p['border']};
}}
"""

    @staticmethod
    def apply_theme(app: QApplication, dark_mode: bool = False) -> None:
        """Register bundled fonts and apply QSS theme to `app`."""
        ThemeManager.register_bundled_fonts()
        app.setStyleSheet(ThemeManager.build_stylesheet(dark_mode=dark_mode))
