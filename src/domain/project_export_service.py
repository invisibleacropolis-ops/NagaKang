"""High-level helper that exports project bundles with manifests and assets."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import shutil
from pathlib import Path
from typing import List, Sequence

from .models import Project
from .persistence import ProjectSerializer
from .project_manifest import (
    MixerSnapshotRecord,
    ProjectManifestBuilder,
    SamplerAssetRecord,
    SamplerManifestIndex,
)


@dataclass(frozen=True)
class MixerSnapshotSpec:
    """Describe a mixer snapshot file that should be bundled."""

    name: str
    path: Path
    snapshot_type: str = "channel"
    destination_name: str | None = None


@dataclass(frozen=True)
class SamplerAssetSpec:
    """Describe a sampler asset that should be copied into the bundle."""

    asset_name: str
    source_path: Path


@dataclass(frozen=True)
class ProjectExportResult:
    """Summaries of exported paths useful for logging or tooling."""

    bundle_root: Path
    manifest_path: Path
    pattern_paths: List[Path] = field(default_factory=list)
    mixer_snapshot_paths: List[Path] = field(default_factory=list)
    sampler_asset_paths: List[Path] = field(default_factory=list)


class ProjectExportService:
    """Serialize projects, mixer snapshots, and sampler assets in one step."""

    def __init__(self, *, sampler_manifest: SamplerManifestIndex | None = None) -> None:
        self._sampler_manifest = sampler_manifest

    def export_project(
        self,
        project: Project,
        *,
        bundle_root: Path,
        snapshot_specs: Sequence[MixerSnapshotSpec] | None = None,
        asset_specs: Sequence[SamplerAssetSpec] | None = None,
        write_project_copy: bool = True,
    ) -> ProjectExportResult:
        bundle_root.mkdir(parents=True, exist_ok=True)
        builder = ProjectManifestBuilder(project, base_path=bundle_root)

        pattern_paths = self._export_patterns(project, bundle_root, builder)
        snapshot_paths = self._export_snapshots(snapshot_specs or [], bundle_root, builder)
        asset_paths = self._export_assets(asset_specs or [], bundle_root, builder)

        manifest_path = builder.write(bundle_root / "project_manifest.json")
        if write_project_copy:
            self._write_project_document(project, bundle_root / "project.json")

        return ProjectExportResult(
            bundle_root=bundle_root,
            manifest_path=manifest_path,
            pattern_paths=pattern_paths,
            mixer_snapshot_paths=snapshot_paths,
            sampler_asset_paths=asset_paths,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _write_project_document(self, project: Project, destination: Path) -> None:
        payload = ProjectSerializer.to_dict(project)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _export_patterns(
        self,
        project: Project,
        bundle_root: Path,
        builder: ProjectManifestBuilder,
    ) -> List[Path]:
        exports: List[Path] = []
        patterns_dir = bundle_root / "patterns"
        patterns_dir.mkdir(parents=True, exist_ok=True)
        for pattern_id in sorted(project.patterns.keys()):
            pattern = project.patterns[pattern_id]
            destination = patterns_dir / f"{pattern.id}.json"
            destination.write_text(pattern.model_dump_json(indent=2), encoding="utf-8")
            builder.add_pattern_file(pattern.id, destination)
            exports.append(destination)
        return exports

    def _export_snapshots(
        self,
        specs: Sequence[MixerSnapshotSpec],
        bundle_root: Path,
        builder: ProjectManifestBuilder,
    ) -> List[Path]:
        exports: List[Path] = []
        if not specs:
            return exports
        mixer_dir = bundle_root / "mixer"
        mixer_dir.mkdir(parents=True, exist_ok=True)
        for spec in specs:
            if not spec.path.exists():
                raise FileNotFoundError(f"Mixer snapshot '{spec.path}' does not exist")
            destination_name = spec.destination_name or spec.path.name
            destination = mixer_dir / destination_name
            shutil.copy2(spec.path, destination)
            record: MixerSnapshotRecord = builder.add_mixer_snapshot(
                spec.name,
                destination,
                snapshot_type=spec.snapshot_type,
            )
            exports.append(bundle_root / Path(record.path))
        return exports

    def _export_assets(
        self,
        specs: Sequence[SamplerAssetSpec],
        bundle_root: Path,
        builder: ProjectManifestBuilder,
    ) -> List[Path]:
        exports: List[Path] = []
        if not specs:
            return exports
        if self._sampler_manifest is None:
            raise ValueError("Sampler manifest is required when exporting sampler assets")
        assets_dir = bundle_root / "assets"
        for spec in specs:
            if not spec.source_path.exists():
                raise FileNotFoundError(f"Sampler asset '{spec.source_path}' does not exist")
            record: SamplerAssetRecord = self._sampler_manifest.copy_asset(
                asset_name=spec.asset_name,
                source_path=spec.source_path,
                destination_dir=assets_dir,
                relative_to=bundle_root,
            )
            builder.add_sampler_asset(record)
            exports.append(bundle_root / record.relative_path)
        return exports


__all__ = [
    "MixerSnapshotSpec",
    "SamplerAssetSpec",
    "ProjectExportResult",
    "ProjectExportService",
]
