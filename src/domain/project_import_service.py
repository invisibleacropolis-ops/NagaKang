"""Helpers that hydrate project bundles exported via :mod:`project_export_service`."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
from typing import List

from .models import Project
from .persistence import ProjectSerializer
from .project_manifest import (
    MixerSnapshotRecord,
    PatternFileRecord,
    ProjectManifest,
    SamplerAssetRecord,
    compute_file_sha256,
)


@dataclass(frozen=True)
class ImportedPattern:
    """Record describing a restored pattern JSON file."""

    record: PatternFileRecord
    path: Path


@dataclass(frozen=True)
class ImportedMixerSnapshot:
    """Record describing a restored mixer snapshot."""

    record: MixerSnapshotRecord
    path: Path


@dataclass(frozen=True)
class ImportedSamplerAsset:
    """Record describing a restored sampler asset."""

    record: SamplerAssetRecord
    path: Path


@dataclass(frozen=True)
class ProjectImportResult:
    """Summary describing the hydrated bundle contents."""

    manifest: ProjectManifest
    manifest_path: Path
    manifest_sha256: str
    project: Project | None
    patterns: List[ImportedPattern] = field(default_factory=list)
    mixer_snapshots: List[ImportedMixerSnapshot] = field(default_factory=list)
    sampler_assets: List[ImportedSamplerAsset] = field(default_factory=list)
    copied_root: Path | None = None

    @property
    def asset_names(self) -> List[str]:
        return [asset.record.asset_name for asset in self.sampler_assets]


class ProjectImportService:
    """Load and validate exported bundles destined for musician testers."""

    def import_bundle(
        self,
        bundle_root: Path,
        *,
        destination_root: Path | None = None,
        manifest_filename: str = "project_manifest.json",
        project_filename: str = "project.json",
    ) -> ProjectImportResult:
        bundle_root = Path(bundle_root)
        manifest_path = bundle_root / manifest_filename
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Manifest '{manifest_path}' not found; verify bundle_root is correct."
            )
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ProjectManifest.model_validate(manifest_payload)
        manifest_sha = compute_file_sha256(manifest_path)

        project_path = bundle_root / project_filename
        project: Project | None = None
        if project_path.exists():
            project_payload = json.loads(project_path.read_text(encoding="utf-8"))
            project = ProjectSerializer.from_dict(project_payload)

        copied_root = None
        if destination_root is not None:
            copied_root = Path(destination_root)
            copied_root.mkdir(parents=True, exist_ok=True)

        imported_patterns = [
            self._import_pattern(bundle_root, record, copied_root)
            for record in manifest.patterns
        ]
        imported_snapshots = [
            self._import_snapshot(bundle_root, record, copied_root)
            for record in manifest.mixer_snapshots
        ]
        imported_assets = [
            self._import_asset(bundle_root, record, copied_root)
            for record in manifest.sampler_assets
        ]

        if copied_root is not None:
            self._copy_optional(bundle_root / project_filename, copied_root / project_filename)
            self._copy_optional(manifest_path, copied_root / manifest_filename)

        return ProjectImportResult(
            manifest=manifest,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha,
            project=project,
            patterns=imported_patterns,
            mixer_snapshots=imported_snapshots,
            sampler_assets=imported_assets,
            copied_root=copied_root,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _import_pattern(
        self,
        bundle_root: Path,
        record: PatternFileRecord,
        copied_root: Path | None,
    ) -> ImportedPattern:
        source = self._resolve(bundle_root, record.path)
        self._verify_checksum(source, record.sha256, label=f"Pattern {record.pattern_id}")
        destination = self._copy_relative(source, copied_root, record.path)
        return ImportedPattern(record=record, path=destination or source)

    def _import_snapshot(
        self,
        bundle_root: Path,
        record: MixerSnapshotRecord,
        copied_root: Path | None,
    ) -> ImportedMixerSnapshot:
        source = self._resolve(bundle_root, record.path)
        self._verify_checksum(source, record.sha256, label=f"Snapshot {record.name}")
        destination = self._copy_relative(source, copied_root, record.path)
        return ImportedMixerSnapshot(record=record, path=destination or source)

    def _import_asset(
        self,
        bundle_root: Path,
        record: SamplerAssetRecord,
        copied_root: Path | None,
    ) -> ImportedSamplerAsset:
        source = self._resolve(bundle_root, record.relative_path)
        self._verify_checksum(source, record.sha256, label=f"Asset {record.asset_name}")
        destination = self._copy_relative(source, copied_root, record.relative_path)
        return ImportedSamplerAsset(record=record, path=destination or source)

    @staticmethod
    def _resolve(bundle_root: Path, relative_path: str) -> Path:
        path = bundle_root / Path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Expected file '{relative_path}' inside bundle")
        return path

    @staticmethod
    def _copy_relative(source: Path, copied_root: Path | None, relative_path: str) -> Path | None:
        if copied_root is None:
            return None
        destination = copied_root / Path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    @staticmethod
    def _copy_optional(source: Path, destination: Path) -> None:
        if not source.exists():
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    @staticmethod
    def _verify_checksum(path: Path, expected_sha: str, *, label: str) -> None:
        actual = compute_file_sha256(path)
        if actual != expected_sha:
            raise ValueError(
                f"{label} checksum mismatch; expected {expected_sha} but found {actual}"
            )


__all__ = [
    "ImportedPattern",
    "ImportedMixerSnapshot",
    "ImportedSamplerAsset",
    "ProjectImportResult",
    "ProjectImportService",
]
