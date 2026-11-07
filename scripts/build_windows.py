"""Standalone Windows Packaging & Post-Build Verification Pipeline for Question Paper Studio.

Automates:
1. Verification/generation of bundled offline assets (`assets/fonts`, `assets/icons`, `assets/templates`, `assets/math`).
2. PyInstaller `--onedir` compilation of `src/main.py` into `dist/QuestionPaperStudio/QuestionPaperStudio.exe`
   with `--windowed`, application icon, bundled `assets/`, `latex2mathml` symbols, `python-docx` templates,
   and `PySide6.QtWebEngineWidgets` / `QtPrintSupport` hooks.
3. Post-build verification executing the compiled binary with `--version` and `--self-test` flags
   and asserting exit code 0.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_NAME = "QuestionPaperStudio"
ENTRYPOINT = PROJECT_ROOT / "src" / "main.py"
ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_PATH = ASSETS_DIR / "icons" / "app_icon.ico"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
ISS_SCRIPT = PROJECT_ROOT / "scripts" / "installer.iss"


def get_expected_executable_path(dist_dir: Path = DIST_DIR) -> Path:
    """Return the expected path to the compiled executable inside `dist/QuestionPaperStudio/`."""
    exe_name = f"{APP_NAME}.exe" if platform.system().lower().startswith("win") else APP_NAME
    return dist_dir / APP_NAME / exe_name


def build_pyinstaller_command(
    clean: bool = True,
    dist_dir: Path = DIST_DIR,
    work_dir: Path = BUILD_DIR,
) -> List[str]:
    """Construct the exact PyInstaller CLI command for `--onedir` windowed packaging."""
    sep = ";" if os.name == "nt" else ":"

    cmd: List[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--name={APP_NAME}",
        f"--distpath={dist_dir}",
        f"--workpath={work_dir}",
        f"--specpath={work_dir}",
        f"--paths={PROJECT_ROOT}",
        f"--add-data={ASSETS_DIR}{sep}assets",
        "--collect-data=latex2mathml",
        "--collect-data=docx",
        "--hidden-import=PySide6.QtPrintSupport",
        "--hidden-import=PySide6.QtWebEngineWidgets",
        "--hidden-import=PySide6.QtWebEngineCore",
        "--hidden-import=PySide6.QtWebChannel",
        "--exclude-module=pytest",
        "--exclude-module=pytest_qt",
        "--exclude-module=django",
        "--exclude-module=tkinter",
    ]

    if clean:
        cmd.append("--clean")

    if ICON_PATH.exists():
        cmd.append(f"--icon={ICON_PATH}")

    cmd.append(str(ENTRYPOINT))
    return cmd


def ensure_assets_ready() -> None:
    """Ensure all required offline fonts, icons, math XSLT, and default templates exist."""
    from scripts.generate_default_assets import generate_all_assets

    if not ICON_PATH.exists() or not (ASSETS_DIR / "templates").exists():
        print("[Build] Generating default offline assets...")
        generate_all_assets()
    else:
        print(f"[Build] Verified bundled assets directory: {ASSETS_DIR}")


def verify_executable(exe_path: Path) -> bool:
    """Verify that the compiled executable exists and passes `--version` and `--self-test` checks."""
    if not exe_path.exists():
        print(f"[Error] Expected executable not found at: {exe_path}", file=sys.stderr)
        return False

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[Verify] Found compiled executable: {exe_path} ({size_mb:.2f} MB)")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"

    # 1. Verify --version flag
    print(f"[Verify] Running: {exe_path.name} --version")
    res_ver = subprocess.run(
        [str(exe_path), "--version"],
        cwd=str(exe_path.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if res_ver.returncode != 0:
        print(f"[Error] --version check failed with code {res_ver.returncode}: {res_ver.stderr}", file=sys.stderr)
        return False
    print(f"[Verify] --version exited 0 (stdout: {res_ver.stdout.strip() or 'windowed subsystem ok'})")

    # 2. Verify --self-test flag
    print(f"[Verify] Running: {exe_path.name} --self-test")
    res_test = subprocess.run(
        [str(exe_path), "--self-test"],
        cwd=str(exe_path.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if res_test.returncode != 0:
        print(
            f"[Error] --self-test failed with exit code {res_test.returncode}:\n"
            f"STDOUT:\n{res_test.stdout}\nSTDERR:\n{res_test.stderr}",
            file=sys.stderr,
        )
        return False

    print("[Verify] Compiled executable passed --self-test with exit code 0!")
    return True


def run_build(skip_pyinstaller: bool = False) -> int:
    """Execute the full Windows `--onedir` packaging and verification pipeline."""
    print("=" * 68)
    print("Question Paper Studio — Windows Packaging Pipeline (PyInstaller)")
    print("=" * 68)

    ensure_assets_ready()
    exe_path = get_expected_executable_path()

    if not skip_pyinstaller:
        cmd = build_pyinstaller_command(clean=True)
        print("[Build] Invoking PyInstaller (--onedir --windowed)...")
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if proc.returncode != 0:
            print(f"[Error] PyInstaller exited with non-zero code: {proc.returncode}", file=sys.stderr)
            return proc.returncode

    if not verify_executable(exe_path):
        return 1

    print("=" * 68)
    print(f"SUCCESS: Standalone distribution ready at: {exe_path.parent}")
    print(f"Inno Setup script ready at:               {ISS_SCRIPT}")
    print("=" * 68)
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Question Paper Studio Windows executable.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip PyInstaller compilation and only verify existing dist executable.",
    )
    args = parser.parse_args(argv)
    return run_build(skip_pyinstaller=args.verify_only)


if __name__ == "__main__":
    sys.exit(main())
