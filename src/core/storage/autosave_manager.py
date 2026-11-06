"""Periodic Background Autosave, Crash Recovery Detection, and Full Workspace `.zip` Backup/Restore."""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.core.models.project_model import ProjectState
from src.core.storage.qpf_archive import QPFArchive


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RecoveryCandidate:
    """Metadata describing an unrecovered autosave snapshot discovered on startup."""

    project_id: str
    title: str
    saved_at: str
    qpf_snapshot_path: Path
    meta_path: Path


class AutosaveManager:
    """Manages periodic `.qpf` autosave snapshots, crash recovery detection, and full workspace backups."""

    def __init__(self, workspace_dir: Path | str) -> None:
        self.workspace_dir = Path(workspace_dir)
        self.autosave_dir = self.workspace_dir / "autosave"
        self.projects_dir = self.workspace_dir / "projects"
        self.templates_dir = self.workspace_dir / "templates"
        self.autosave_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def perform_autosave(
        self,
        project: ProjectState,
        asset_search_dirs: Optional[List[Path]] = None,
    ) -> Path:
        """Write an atomic `.qpf` autosave snapshot and dirty recovery marker for `project`."""
        safe_id = "".join(c for c in project.project_id if c.isalnum() or c in ("-", "_"))
        snapshot_path = self.autosave_dir / f"{safe_id}.autosave.qpf"
        meta_path = self.autosave_dir / f"{safe_id}.recovery.json"

        QPFArchive.save_qpf(
            project,
            dest_path=snapshot_path,
            overwrite=True,
            asset_search_dirs=asset_search_dirs,
        )

        now_iso = _utc_now().isoformat()
        meta_payload = {
            "project_id": project.project_id,
            "title": project.title,
            "saved_at": now_iso,
            "snapshot_file": snapshot_path.name,
            "clean_exit": False,
        }
        meta_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
        return snapshot_path

    def mark_clean_close(self, project_id: str) -> None:
        """Clear the dirty crash recovery marker when a project is explicitly saved or closed cleanly."""
        safe_id = "".join(c for c in project_id if c.isalnum() or c in ("-", "_"))
        snapshot_path = self.autosave_dir / f"{safe_id}.autosave.qpf"
        meta_path = self.autosave_dir / f"{safe_id}.recovery.json"
        if meta_path.exists():
            meta_path.unlink()
        if snapshot_path.exists():
            snapshot_path.unlink()

    def list_unrecovered_snapshots(self) -> List[RecoveryCandidate]:
        """Scan `self.autosave_dir` for dirty recovery markers left behind by an unexpected exit."""
        candidates: List[RecoveryCandidate] = []
        for meta_path in sorted(self.autosave_dir.glob("*.recovery.json")):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if data.get("clean_exit") is True:
                    continue
                snap_file = self.autosave_dir / str(data.get("snapshot_file", ""))
                if not snap_file.exists():
                    continue
                candidates.append(
                    RecoveryCandidate(
                        project_id=str(data["project_id"]),
                        title=str(data.get("title", "Recovered Question Paper")),
                        saved_at=str(data.get("saved_at", "")),
                        qpf_snapshot_path=snap_file,
                        meta_path=meta_path,
                    )
                )
            except Exception:
                continue
        return candidates

    def recover_project(
        self,
        candidate: RecoveryCandidate,
        extract_assets_to: Optional[Path | str] = None,
    ) -> ProjectState:
        """Restore a `ProjectState` from a `RecoveryCandidate` snapshot."""
        unpack_res = QPFArchive.load_qpf(
            candidate.qpf_snapshot_path,
            extract_assets_to=extract_assets_to,
        )
        return unpack_res.project

    def create_workspace_backup(self, backup_zip_path: Path | str) -> Path:
        """Create a complete portable `.zip` backup of the workspace (DB, templates, projects, assets)."""
        out_zip = Path(backup_zip_path)
        if out_zip.suffix.lower() != ".zip":
            out_zip = out_zip.with_suffix(".zip")
        out_zip.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(out_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in self.workspace_dir.rglob("*"):
                if item.is_file() and item.resolve() != out_zip.resolve():
                    rel = item.relative_to(self.workspace_dir).as_posix()
                    # Skip activeautosave lock files
                    if rel.startswith("autosave/"):
                        continue
                    zf.write(item, arcname=rel)
        return out_zip

    def restore_workspace_backup(self, backup_zip_path: Path | str) -> List[Path]:
        """Restore a workspace `.zip` backup into `self.workspace_dir`."""
        src_zip = Path(backup_zip_path)
        if not src_zip.exists() or not zipfile.is_zipfile(src_zip):
            raise ValueError(f"Invalid workspace backup archive: '{src_zip}'")

        restored_files: List[Path] = []
        with zipfile.ZipFile(src_zip, mode="r") as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                # Prevent path traversal
                rel_member = Path(member)
                if ".." in rel_member.parts:
                    continue
                dest = self.workspace_dir / rel_member
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src_s, dest.open("wb") as dst_s:
                    shutil.copyfileobj(src_s, dst_s)
                restored_files.append(dest)
        return restored_files
