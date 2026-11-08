"""`.qpf` (Question Paper File) ZIP archive bundler and unpacker with SHA-256 asset deduplication."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.core.models.enums import CanvasElementType
from src.core.models.project_model import ProjectState
from src.core.models.question_model import DiagramLabellingData, QuestionNode

PROJECT_JSON_FILENAME = "project.json"
MANIFEST_JSON_FILENAME = "manifest.json"
ASSETS_ARCHIVE_PREFIX = "assets/"


@dataclass
class QPFUnpackResult:
    """Result of unpacking a `.qpf` project archive."""

    project: ProjectState
    extracted_assets_dir: Path
    asset_map: Dict[str, Path]
    manifest: Dict[str, object]


class QPFArchive:
    """Packs and unpacks `.qpf` ZIP archives containing `project.json` and `assets/`."""

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """Compute the hex SHA-256 digest of a file."""
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _resolve_asset_candidate(
        raw_path: str,
        asset_search_dirs: List[Path],
    ) -> Optional[Path]:
        """Resolve a relative or absolute asset path against candidate directories."""
        if not raw_path or not raw_path.strip():
            return None
        candidate = Path(raw_path)
        if candidate.is_absolute() and candidate.exists() and candidate.is_file():
            return candidate
        for base in asset_search_dirs:
            joined = base / raw_path
            if joined.exists() and joined.is_file():
                return joined
            # Also check by basename inside base or base/assets
            by_name = base / candidate.name
            if by_name.exists() and by_name.is_file():
                return by_name
            in_assets = base / "assets" / candidate.name
            if in_assets.exists() and in_assets.is_file():
                return in_assets
        return None

    @staticmethod
    def save_qpf(
        project: ProjectState,
        dest_path: Path | str,
        overwrite: bool = False,
        asset_search_dirs: Optional[List[Path]] = None,
    ) -> Path:
        """Bundle `project` and all referenced local assets into a `.qpf` ZIP archive.

        Raises `FileExistsError` if `dest_path` already exists and `overwrite=False`.
        """
        out_path = Path(dest_path)
        if out_path.suffix.lower() != ".qpf":
            out_path = out_path.with_suffix(".qpf")

        if out_path.exists() and not overwrite:
            raise FileExistsError(
                f"Project file '{out_path}' already exists. Pass overwrite=True to replace it."
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        search_dirs = list(asset_search_dirs or [])
        search_dirs.append(Path.cwd())

        # Deep-copy the project so path normalization inside the archive does not mutate live UI paths
        archived_project = project.model_copy(deep=True)
        archived_project.updated_at = datetime.now(timezone.utc)

        bundled_files: Dict[str, Path] = {}  # archive_rel_path -> source_file_path
        asset_hashes: Dict[str, str] = {}

        def _bundle_asset_path(raw_path: str) -> str:
            resolved = QPFArchive._resolve_asset_candidate(raw_path, search_dirs)
            if resolved is None:
                return raw_path
            digest = QPFArchive._compute_sha256(resolved)[:16]
            ext = resolved.suffix.lower() or ".bin"
            safe_stem = "".join(c for c in resolved.stem if c.isalnum() or c in ("_", "-"))[:32] or "asset"
            archive_rel = f"{ASSETS_ARCHIVE_PREFIX}{safe_stem}_{digest}{ext}"
            bundled_files[archive_rel] = resolved
            asset_hashes[archive_rel] = digest
            return archive_rel

        # 1. Inspect Template Snapshot image elements & imported backdrop
        tmpl = archived_project.template_snapshot
        if tmpl.imported_backdrop_asset:
            tmpl.imported_backdrop_asset = _bundle_asset_path(tmpl.imported_backdrop_asset)

        for el_list in (
            tmpl.first_page_header_elements,
            tmpl.running_header_elements,
            tmpl.first_page_footer_elements,
            tmpl.running_footer_elements,
        ):
            for el in el_list:
                if el.element_type == CanvasElementType.IMAGE and el.content:
                    el.content = _bundle_asset_path(el.content)

        # 2. Inspect SharedPassages & QuestionNodes recursively
        for sec in archived_project.sections:
            for sp in sec.shared_passages:
                for diag in sp.diagrams:
                    diag.asset_path = _bundle_asset_path(diag.asset_path)

        for qnode in archived_project.all_questions_dfs():
            for diag in qnode.diagrams:
                diag.asset_path = _bundle_asset_path(diag.asset_path)
            if isinstance(qnode.type_data, DiagramLabellingData) and qnode.type_data.diagram_asset_path:
                qnode.type_data.diagram_asset_path = _bundle_asset_path(
                    qnode.type_data.diagram_asset_path
                )

        manifest = {
            "format": "QuestionPaperStudio.QPF",
            "format_version": "1.0",
            "project_id": archived_project.project_id,
            "title": archived_project.title,
            "saved_at": archived_project.updated_at.isoformat(),
            "asset_count": len(bundled_files),
            "assets": asset_hashes,
        }

        with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(PROJECT_JSON_FILENAME, archived_project.to_json_string(indent=2))
            zf.writestr(MANIFEST_JSON_FILENAME, json.dumps(manifest, indent=2))
            for archive_rel, src_file in bundled_files.items():
                zf.write(src_file, arcname=archive_rel)

        return out_path

    @staticmethod
    def load_qpf(
        qpf_path: Path | str,
        extract_assets_to: Optional[Path | str] = None,
    ) -> QPFUnpackResult:
        """Unpack a `.qpf` archive, validate its structure, and restore `ProjectState`."""
        src_path = Path(qpf_path)
        if not src_path.exists():
            raise FileNotFoundError(f"QPF file not found: '{src_path}'")
        if not zipfile.is_zipfile(src_path):
            raise ValueError(f"File is not a valid .qpf ZIP archive: '{src_path}'")

        with zipfile.ZipFile(src_path, mode="r") as zf:
            names = zf.namelist()
            if PROJECT_JSON_FILENAME not in names:
                raise ValueError(f"Invalid .qpf archive (missing {PROJECT_JSON_FILENAME}): '{src_path}'")

            project_json_bytes = zf.read(PROJECT_JSON_FILENAME)
            project = ProjectState.from_json_string(project_json_bytes.decode("utf-8"))

            manifest: Dict[str, object] = {}
            if MANIFEST_JSON_FILENAME in names:
                manifest = json.loads(zf.read(MANIFEST_JSON_FILENAME).decode("utf-8"))

            if extract_assets_to is not None:
                target_root = Path(extract_assets_to)
            else:
                target_root = src_path.parent / f".{src_path.stem}_assets"

            extracted_assets_dir = target_root / "assets"
            asset_map: Dict[str, Path] = {}

            asset_entries = [n for n in names if n.startswith(ASSETS_ARCHIVE_PREFIX) and not n.endswith("/")]
            if asset_entries:
                extracted_assets_dir.mkdir(parents=True, exist_ok=True)
                resolved_assets_root = extracted_assets_dir.resolve()
                for member in asset_entries:
                    rel_after_prefix = member[len(ASSETS_ARCHIVE_PREFIX):]
                    if ".." in Path(rel_after_prefix).parts or rel_after_prefix.startswith(("/", "\\")):
                        raise ValueError(f"Unsafe path traversal entry detected in QPF archive: '{member}'")
                    filename = Path(rel_after_prefix).name
                    if not filename:
                        continue
                    dest_file = (extracted_assets_dir / filename).resolve()
                    if not str(dest_file).startswith(str(resolved_assets_root)):
                        raise ValueError(f"Asset destination escapes extraction directory: '{member}'")
                    with zf.open(member) as src_stream, dest_file.open("wb") as dst_stream:
                        shutil.copyfileobj(src_stream, dst_stream)
                    asset_map[member] = dest_file

        # Rewrite relative archive paths to extracted file paths when assets were extracted
        if asset_map:
            tmpl = project.template_snapshot
            if tmpl.imported_backdrop_asset in asset_map:
                tmpl.imported_backdrop_asset = str(asset_map[tmpl.imported_backdrop_asset])
            for el_list in (
                tmpl.first_page_header_elements,
                tmpl.running_header_elements,
                tmpl.first_page_footer_elements,
                tmpl.running_footer_elements,
            ):
                for el in el_list:
                    if el.element_type == CanvasElementType.IMAGE and el.content in asset_map:
                        el.content = str(asset_map[el.content])

            for sec in project.sections:
                for sp in sec.shared_passages:
                    for diag in sp.diagrams:
                        if diag.asset_path in asset_map:
                            diag.asset_path = str(asset_map[diag.asset_path])

            for qnode in project.all_questions_dfs():
                for diag in qnode.diagrams:
                    if diag.asset_path in asset_map:
                        diag.asset_path = str(asset_map[diag.asset_path])
                if (
                    isinstance(qnode.type_data, DiagramLabellingData)
                    and qnode.type_data.diagram_asset_path in asset_map
                ):
                    qnode.type_data.diagram_asset_path = str(
                        asset_map[qnode.type_data.diagram_asset_path]
                    )

        return QPFUnpackResult(
            project=project,
            extracted_assets_dir=extracted_assets_dir,
            asset_map=asset_map,
            manifest=manifest,
        )
