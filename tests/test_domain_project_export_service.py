from datetime import UTC, datetime
from pathlib import Path

from domain.models import Pattern, PatternStep, Project, ProjectMetadata
from domain.project_export_service import (
    MixerSnapshotSpec,
    ProjectExportService,
    SamplerAssetSpec,
)
from domain.project_manifest import SamplerManifestIndex


def build_project() -> Project:
    metadata = ProjectMetadata(
        id="bundle-demo",
        name="Bundle Demo",
        bpm=128.0,
        swing=0.1,
        created_at=datetime(2025, 11, 25, tzinfo=UTC),
        updated_at=datetime(2025, 11, 25, tzinfo=UTC),
    )
    project = Project(metadata=metadata)
    pattern = Pattern(
        id="hook",
        name="Hook",
        length_steps=16,
        steps=[PatternStep(note=60, velocity=100) for _ in range(8)],
    )
    project.add_pattern(pattern)
    return project


def write_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_export_service_writes_patterns_snapshots_and_assets(tmp_path: Path) -> None:
    project = build_project()
    manifest_payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {
                "name": "choir_pad_soft.wav",
                "sha256": "3957a235fae214722cb1521c7702aca6a4a6deefcbf5f7e221879662ed84cd4b",
            }
        ],
    }
    sampler_manifest = SamplerManifestIndex.from_payload(manifest_payload)
    asset_path = write_file(tmp_path / "imports" / "choir_pad_soft.wav", b"demo-bytes")
    snapshot_path = write_file(tmp_path / "snapshots" / "hook.json", b"{\n  \"meters\": []\n}")

    service = ProjectExportService(sampler_manifest=sampler_manifest)
    result = service.export_project(
        project,
        bundle_root=tmp_path / "bundle",
        snapshot_specs=[
            MixerSnapshotSpec(name="Hook", path=snapshot_path, snapshot_type="master"),
        ],
        asset_specs=[
            SamplerAssetSpec(asset_name="choir_pad_soft.wav", source_path=asset_path),
        ],
    )

    assert (result.bundle_root / "project.json").exists()
    assert (result.bundle_root / "patterns" / "hook.json").exists()
    assert (result.bundle_root / "mixer" / "hook.json").exists()
    assert (result.bundle_root / "assets" / "choir_pad_soft.wav").exists()
    assert result.manifest_path.exists()

    manifest_data = result.manifest_path.read_text(encoding="utf-8")
    assert "choir_pad_soft.wav" in manifest_data
    assert "Hook" in manifest_data


def test_export_service_requires_manifest_for_assets(tmp_path: Path) -> None:
    project = build_project()
    service = ProjectExportService()
    asset_path = write_file(tmp_path / "imports" / "asset.wav", b"asset-bytes")

    try:
        service.export_project(
            project,
            bundle_root=tmp_path / "bundle",
            asset_specs=[SamplerAssetSpec(asset_name="asset.wav", source_path=asset_path)],
        )
    except ValueError as exc:
        assert "Sampler manifest" in str(exc)
    else:  # pragma: no cover - defensive guard to make assertion explicit
        raise AssertionError("Expected ValueError when exporting assets without manifest")
