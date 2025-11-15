"""Step 8 project manifest schema plus asset import/export helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import List, Mapping, Sequence

from pydantic import BaseModel, Field

from .models import Pattern, Project


class ProjectSummary(BaseModel):
    """Human-readable snapshot of project metadata stored in manifests."""

    id: str
    name: str
    bpm: float
    swing: float
    created_at: datetime
    updated_at: datetime


class PatternFileRecord(BaseModel):
    """Describe where a serialized pattern lives plus integrity metadata."""

    pattern_id: str
    path: str = Field(description="Relative path inside the project bundle")
    sha256: str
    length_steps: int
    step_count: int


class MixerSnapshotRecord(BaseModel):
    """Reference to a mixer snapshot JSON export plus checksum."""

    name: str
    path: str
    sha256: str
    snapshot_type: str = Field(
        "channel",
        description="Logical grouping of the snapshot (channel, subgroup, master)",
    )


class SamplerAssetRecord(BaseModel):
    """Asset entry capturing audio sample provenance and LUFS metadata."""

    asset_name: str
    relative_path: str
    sha256: str
    lufs_lu: float | None = Field(
        None, description="Integrated LUFS reported by the sampler manifest"
    )
    source_uri: str | None = Field(
        None, description="Cloud URI or NAS path that hosted the canonical asset"
    )


class ProjectManifest(BaseModel):
    """Versioned manifest referencing tracker, mixer, and sampler artifacts."""

    manifest_version: str = Field("1.0.0", description="Semantic version of schema")
    project: ProjectSummary
    patterns: List[PatternFileRecord] = Field(default_factory=list)
    mixer_snapshots: List[MixerSnapshotRecord] = Field(default_factory=list)
    sampler_assets: List[SamplerAssetRecord] = Field(default_factory=list)


class ProjectManifestBuilder:
    """Collect manifest records for a Project before serialization."""

    def __init__(
        self,
        project: Project,
        *,
        base_path: Path | None = None,
        manifest_version: str = "1.0.0",
    ) -> None:
        self._project = project
        self._base_path = base_path
        self._manifest_version = manifest_version
        self._patterns: dict[str, PatternFileRecord] = {}
        self._snapshots: List[MixerSnapshotRecord] = []
        self._assets: List[SamplerAssetRecord] = []

    def _relative_path(self, path: Path) -> str:
        normalized = Path(path)
        if self._base_path is None:
            return normalized.as_posix()
        try:
            return normalized.resolve().relative_to(self._base_path.resolve()).as_posix()
        except ValueError:
            return normalized.as_posix()

    def add_pattern_file(
        self,
        pattern_id: str,
        path: Path,
        *,
        sha256: str | None = None,
        step_count: int | None = None,
    ) -> PatternFileRecord:
        """Record a serialized pattern export inside the manifest."""

        if pattern_id not in self._project.patterns:
            raise KeyError(f"Pattern {pattern_id!r} not found in project")
        pattern: Pattern = self._project.patterns[pattern_id]
        record = PatternFileRecord(
            pattern_id=pattern_id,
            path=self._relative_path(path),
            sha256=sha256 or compute_file_sha256(path),
            length_steps=pattern.length_steps,
            step_count=step_count if step_count is not None else len(pattern.steps),
        )
        self._patterns[pattern_id] = record
        return record

    def add_mixer_snapshot(
        self,
        name: str,
        path: Path,
        *,
        snapshot_type: str = "channel",
        sha256: str | None = None,
    ) -> MixerSnapshotRecord:
        """Record a mixer snapshot export for later import/export flows."""

        record = MixerSnapshotRecord(
            name=name,
            path=self._relative_path(path),
            sha256=sha256 or compute_file_sha256(path),
            snapshot_type=snapshot_type,
        )
        self._snapshots.append(record)
        return record

    def add_sampler_asset(self, record: SamplerAssetRecord) -> None:
        """Append an audio asset record, ensuring deterministic ordering."""

        self._assets.append(record)

    def build(self) -> ProjectManifest:
        """Assemble the :class:`ProjectManifest` dataclass."""

        metadata = self._project.metadata
        summary = ProjectSummary(
            id=metadata.id,
            name=metadata.name,
            bpm=metadata.bpm,
            swing=metadata.swing,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )
        return ProjectManifest(
            manifest_version=self._manifest_version,
            project=summary,
            patterns=sorted(self._patterns.values(), key=lambda record: record.pattern_id),
            mixer_snapshots=list(self._snapshots),
            sampler_assets=list(self._assets),
        )

    def write(self, destination: Path) -> Path:
        """Serialize the manifest to ``destination`` and return the path."""

        manifest = self.build()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return destination


class SamplerManifestAsset(BaseModel):
    """Single entry inside the canonical sampler manifest JSON export."""

    name: str
    nas_path: str | None = None
    s3_uri: str | None = None
    lufs: float | None = None
    peak_dbfs: float | None = None
    sha256: str


class SamplerManifestIndex(BaseModel):
    """In-memory helper for sampler manifest lookups and copy automation."""

    bucket: str
    prefix: str
    last_updated: datetime
    assets: List[SamplerManifestAsset]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SamplerManifestIndex":
        """Hydrate from a raw dict (loaded JSON)."""

        return cls.model_validate(payload)

    @classmethod
    def from_file(cls, path: Path) -> "SamplerManifestIndex":
        """Load a sampler manifest JSON export from disk."""

        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_payload(payload)

    def dialog_filters(self) -> List[Mapping[str, Sequence[str]]]:
        """Return file-dialog filters referencing manifest extensions."""

        extensions = sorted({Path(asset.name).suffix or "" for asset in self.assets})
        patterns = [f"*{ext}" if ext else "*" for ext in extensions]
        return [
            {
                "label": "Sampler Assets",
                "patterns": patterns or ["*.wav", "*.flac"],
            }
        ]

    def _asset_by_name(self, asset_name: str) -> SamplerManifestAsset:
        for asset in self.assets:
            if asset.name == asset_name:
                return asset
        raise KeyError(f"Asset {asset_name!r} not found in sampler manifest")

    def _asset_by_sha(self, sha256: str) -> SamplerManifestAsset:
        for asset in self.assets:
            if asset.sha256 == sha256:
                return asset
        raise KeyError(f"Asset with sha {sha256} not found in sampler manifest")

    def copy_asset(
        self,
        *,
        asset_name: str | None = None,
        sha256: str | None = None,
        source_path: Path,
        destination_dir: Path,
        relative_to: Path | None = None,
    ) -> SamplerAssetRecord:
        """Copy an asset referenced by the manifest and record metadata."""

        if asset_name is None and sha256 is None:
            raise ValueError("Provide either asset_name or sha256")
        checksum = compute_file_sha256(source_path)
        asset: SamplerManifestAsset
        if asset_name is not None:
            asset = self._asset_by_name(asset_name)
        else:
            asset = self._asset_by_sha(sha256 or checksum)
        if asset.sha256 != checksum:
            raise ValueError(
                "Source file checksum mismatch; expected "
                f"{asset.sha256} but got {checksum}"
            )
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / asset.name
        shutil.copy2(source_path, destination_path)
        relative_path = destination_path.as_posix()
        if relative_to is not None:
            try:
                relative_path = (
                    destination_path.resolve().relative_to(relative_to.resolve()).as_posix()
                )
            except ValueError:
                relative_path = destination_path.as_posix()
        return SamplerAssetRecord(
            asset_name=asset.name,
            relative_path=relative_path,
            sha256=checksum,
            lufs_lu=asset.lufs,
            source_uri=asset.s3_uri or asset.nas_path,
        )


def compute_file_sha256(path: Path) -> str:
    """Return the SHA-256 digest for ``path``."""

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass(frozen=True)
class ProjectImportPlan:
    """Lightweight container summarizing import dialog expectations."""

    dialog_filters: List[Mapping[str, Sequence[str]]]
    asset_count: int


def build_import_plan(manifest: SamplerManifestIndex) -> ProjectImportPlan:
    """Return a high-level plan describing UI file-dialog scaffolding."""

    filters = manifest.dialog_filters()
    return ProjectImportPlan(dialog_filters=filters, asset_count=len(manifest.assets))
