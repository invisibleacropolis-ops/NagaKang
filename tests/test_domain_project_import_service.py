from datetime import UTC, datetime
from pathlib import Path

from domain.models import Pattern, PatternStep, Project, ProjectMetadata
from domain.project_export_service import (
    MixerSnapshotSpec,
    ProjectExportService,
    SamplerAssetSpec,
)
from domain.project_import_service import ProjectImportService
from domain.project_manifest import SamplerManifestIndex


def build_project() -> Project:
    metadata = ProjectMetadata(
        id="bundle-demo",
        name="Bundle Demo",
        bpm=124.0,
        swing=0.12,
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


def export_bundle(tmp_path: Path) -> Path:
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
    snapshot_path = write_file(tmp_path / "snapshots" / "hook.json", b"{}")
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
    return result.bundle_root


def test_import_service_restores_bundle(tmp_path: Path) -> None:
    bundle_root = export_bundle(tmp_path)
    destination = tmp_path / "restored"

    importer = ProjectImportService()
    result = importer.import_bundle(bundle_root, destination_root=destination)

    assert result.project is not None
    assert result.project.metadata.id == "bundle-demo"
    assert result.manifest.project.name == "Bundle Demo"
    assert result.manifest_sha256
    assert len(result.patterns) == 1
    assert len(result.mixer_snapshots) == 1
    assert len(result.sampler_assets) == 1
    restored_manifest = destination / "project_manifest.json"
    assert restored_manifest.exists()
    assert (destination / "patterns" / "hook.json").exists()
    assert (destination / "assets" / "choir_pad_soft.wav").exists()


def test_import_service_validates_checksums(tmp_path: Path) -> None:
    bundle_root = export_bundle(tmp_path)
    pattern_path = bundle_root / "patterns" / "hook.json"
    pattern_path.write_text("{}", encoding="utf-8")

    importer = ProjectImportService()
    try:
        importer.import_bundle(bundle_root)
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:  # pragma: no cover - explicit failure signal
        raise AssertionError("Expected checksum validation failure")
