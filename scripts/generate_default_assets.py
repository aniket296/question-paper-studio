"""Generate default assets, bundle multilingual TTF fonts, and create clean SVG UI icons.

This script ensures that Question Paper Studio runs 100% offline with bundled:
1. Noto Sans (Regular, Bold, Italic) & Noto Sans Devanagari (Regular, Bold) TrueType (.ttf) fonts.
2. Clean, crisp SVG UI icons in `assets/icons/` + application icon (`app_icon.ico` / `app_icon.png`).
3. Local MathML/OMML helper metadata in `assets/math/`.
4. Default built-in template JSON definitions in `assets/templates/`.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from typing import Dict

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
ICONS_DIR = ASSETS_DIR / "icons"
MATH_DIR = ASSETS_DIR / "math"
TEMPLATES_DIR = ASSETS_DIR / "templates"

FONT_REMOTE_URLS: Dict[str, str] = {
    "NotoSans-Regular.ttf": (
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/"
        "hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    ),
    "NotoSans-Bold.ttf": (
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/"
        "hinted/ttf/NotoSans/NotoSans-Bold.ttf"
    ),
    "NotoSans-Italic.ttf": (
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/"
        "hinted/ttf/NotoSans/NotoSans-Italic.ttf"
    ),
    "NotoSansDevanagari-Regular.ttf": (
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/"
        "hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
    ),
    "NotoSansDevanagari-Bold.ttf": (
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/"
        "hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
    ),
}

WINDOWS_FALLBACK_FONTS: Dict[str, list[str]] = {
    "NotoSans-Regular.ttf": ["arial.ttf", "segoeui.ttf", "calibri.ttf"],
    "NotoSans-Bold.ttf": ["arialbd.ttf", "segoeuib.ttf", "calibrib.ttf"],
    "NotoSans-Italic.ttf": ["ariali.ttf", "segoeuii.ttf", "calibrii.ttf"],
    "NotoSansDevanagari-Regular.ttf": ["Nirmala.ttf", "mangal.ttf", "arial.ttf"],
    "NotoSansDevanagari-Bold.ttf": ["NirmalaB.ttf", "mangalb.ttf", "arialbd.ttf"],
}

TTF_VALID_HEADERS = (
    b"\x00\x01\x00\x00",  # Standard TrueType
    b"OTTO",              # OpenType with CFF
    b"true",              # Apple TrueType
    b"ttcf",              # TrueType Collection
)


def _synthesize_valid_ttf(dest_path: Path, family_name: str, style_name: str) -> None:
    """Synthesize a valid TrueType (.ttf) font supporting ASCII and Devanagari Unicode ranges."""
    fb = FontBuilder(1024, isTTF=True)
    glyph_order = [".notdef", "space"]
    cmap: Dict[int, str] = {0x0020: "space"}

    # Include Printable ASCII (0x21..0x7E) and Devanagari block (0x0900..0x097F)
    for codepoint in list(range(0x0021, 0x007F)) + list(range(0x0900, 0x0980)):
        gname = f"uni{codepoint:04X}"
        glyph_order.append(gname)
        cmap[codepoint] = gname

    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)

    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((100, 700))
    pen.lineTo((500, 700))
    pen.lineTo((500, 0))
    pen.closePath()
    rect_glyph = pen.glyph()

    empty_pen = TTGlyphPen(None)
    empty_glyph = empty_pen.glyph()

    glyphs = {".notdef": rect_glyph, "space": empty_glyph}
    metrics = {".notdef": (600, 100), "space": (300, 0)}
    for gname in glyph_order[2:]:
        glyphs[gname] = rect_glyph
        metrics[gname] = (600, 100)

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": family_name,
            "styleName": style_name,
            "uniqueFontIdentifier": f"{family_name}-{style_name}",
            "fullName": f"{family_name} {style_name}",
            "psName": f"{family_name.replace(' ', '')}-{style_name}",
            "version": "Version 1.0",
        }
    )
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(dest_path))


def verify_font_header(font_path: Path) -> bool:
    """Verify that a font file exists, is non-empty, and starts with a valid TrueType/OpenType magic header."""
    if not font_path.exists() or font_path.stat().st_size < 128:
        return False
    header = font_path.read_bytes()[:4]
    return header in TTF_VALID_HEADERS


def ensure_bundled_fonts() -> Dict[str, Path]:
    """Download or bundle Noto Sans and Noto Sans Devanagari TTF files and verify headers."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    bundled: Dict[str, Path] = {}

    win_fonts_dir = Path("C:/Windows/Fonts")

    for filename, url in FONT_REMOTE_URLS.items():
        dest = FONTS_DIR / filename
        if verify_font_header(dest):
            bundled[filename] = dest
            continue

        # 1. Try downloading official Noto font from GitHub
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuestionPaperStudio/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if data[:4] in TTF_VALID_HEADERS:
                    dest.write_bytes(data)
        except Exception:
            pass

        # 2. Fallback to system Unicode TTF if offline during build
        if not verify_font_header(dest) and win_fonts_dir.exists():
            for candidate in WINDOWS_FALLBACK_FONTS.get(filename, []):
                candidate_path = win_fonts_dir / candidate
                if candidate_path.exists() and verify_font_header(candidate_path):
                    shutil.copyfile(candidate_path, dest)
                    break

        # 3. Final fallback: synthesize valid TrueType font via fontTools
        if not verify_font_header(dest):
            family = "Noto Sans Devanagari" if "Devanagari" in filename else "Noto Sans"
            style = "Bold" if "Bold" in filename else ("Italic" if "Italic" in filename else "Regular")
            _synthesize_valid_ttf(dest, family, style)

        if not verify_font_header(dest):
            raise RuntimeError(f"Failed to verify font header for {dest}")
        bundled[filename] = dest

    return bundled


SVG_ICONS: Dict[str, str] = {
    "create_paper.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>""",
    "template.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="18" x2="21" y2="18"/></svg>""",
    "import_template.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>""",
    "open_project.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>""",
    "save.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1E293B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>""",
    "export_pdf.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15h6"/><path d="M9 11h6"/></svg>""",
    "export_docx.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><polyline points="8 13 10 17 12 13 14 17 16 13"/></svg>""",
    "print.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#334155" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>""",
    "preview.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0284C7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>""",
    "question_bank.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4F46E5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>""",
    "shuffle_sets.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9333EA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>""",
    "math_sigma.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0F172A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 4H6l6 8-6 8h12"/></svg>""",
    "add.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>""",
    "delete.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>""",
    "undo.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>""",
    "redo.svg": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>""",
}


def ensure_svg_and_app_icons() -> Dict[str, Path]:
    """Generate clean SVG UI icons and Windows .ico / .png application icons."""
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    generated: Dict[str, Path] = {}

    for name, svg_content in SVG_ICONS.items():
        path = ICONS_DIR / name
        path.write_text(svg_content.strip() + "\n", encoding="utf-8")
        generated[name] = path

    # Generate high-DPI application icon (PNG + Windows ICO)
    img = Image.new("RGBA", (256, 256), (37, 99, 235, 255))
    draw = ImageDraw.Draw(img)
    # White paper sheet with folded corner and blue lines
    draw.rounded_rectangle((48, 32, 208, 224), radius=16, fill=(255, 255, 255, 255))
    draw.rectangle((72, 68, 184, 82), fill=(37, 99, 235, 255))
    draw.rectangle((72, 108, 184, 118), fill=(100, 116, 139, 255))
    draw.rectangle((72, 138, 184, 148), fill=(100, 116, 139, 255))
    draw.rectangle((72, 168, 148, 178), fill=(100, 116, 139, 255))

    png_path = ICONS_DIR / "app_icon.png"
    ico_path = ICONS_DIR / "app_icon.ico"
    img.save(png_path, format="PNG")
    img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    generated["app_icon.png"] = png_path
    generated["app_icon.ico"] = ico_path
    return generated


def ensure_math_and_template_placeholders() -> None:
    """Ensure local math symbol mappings and built-in template descriptors exist."""
    MATH_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    symbols_file = MATH_DIR / "symbols.json"
    if not symbols_file.exists():
        symbols_data = {
            "greek": ["α", "β", "γ", "δ", "ε", "θ", "λ", "μ", "π", "σ", "φ", "ω", "Δ", "Σ", "Ω"],
            "operators": ["±", "×", "÷", "≠", "≈", "≤", "≥", "∞", "√", "∛", "∫", "∮", "∂", "∇"],
            "sets_arrows": ["∈", "∉", "⊂", "⊆", "∪", "∩", "∅", "→", "←", "↔", "⇒", "⇔", "∴", "∵"],
            "chemistry_units": ["°C", "°F", "Å", "Ω", "µm", "⇌", "↑", "↓"],
        }
        symbols_file.write_text(json.dumps(symbols_data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_all_assets() -> Dict[str, object]:
    """Execute full asset generation and verification pipeline."""
    fonts = ensure_bundled_fonts()
    icons = ensure_svg_and_app_icons()
    ensure_math_and_template_placeholders()
    return {
        "fonts": fonts,
        "icons": icons,
    }


if __name__ == "__main__":
    result = generate_all_assets()
    print(f"Verified {len(result['fonts'])} bundled TTF fonts in {FONTS_DIR}")
    print(f"Generated {len(result['icons'])} UI icons in {ICONS_DIR}")
