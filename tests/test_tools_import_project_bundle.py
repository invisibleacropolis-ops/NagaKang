import json
from pathlib import Path

from domain.models import Pattern, PatternStep, Project, ProjectMetadata
from domain.project_export_service import ProjectExportService
from domain.project_export_service import SamplerAssetSpec, MixerSnapshotSpec
from domain.project_manifest import SamplerManifestIndex

from tools import import_project_bundle


def build_project() -> Project:
    metadata = ProjectMetadata(id="cli-demo", name="CLI Demo")
    project = Project(metadata=metadata)
    pattern = Pattern(id="hook", name="Hook", length_steps=8, steps=[PatternStep() for _ in range(8)])
    project.add_pattern(pattern)
    return project


def write_manifest(tmp_path: Path, asset_name: str) -> SamplerManifestIndex:
    payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {
                "name": asset_name,
                "sha256": "3957a235fae214722cb1521c7702aca6a4a6deefcbf5f7e221879662ed84cd4b",
            }
        ],
    }
    return SamplerManifestIndex.from_payload(payload)


def export_bundle(tmp_path: Path) -> Path:
    project = build_project()
    manifest = write_manifest(tmp_path, "choir.wav")
    asset_source = tmp_path / "imports" / "choir.wav"
    asset_source.parent.mkdir(parents=True, exist_ok=True)
    asset_source.write_bytes(b"demo-bytes")
    snapshot = tmp_path / "snapshots" / "hook.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{}", encoding="utf-8")

    service = ProjectExportService(sampler_manifest=manifest)
    service.export_project(
        project,
        bundle_root=tmp_path / "bundle",
        snapshot_specs=[MixerSnapshotSpec(name="Hook", path=snapshot)],
        asset_specs=[SamplerAssetSpec(asset_name="choir.wav", source_path=asset_source)],
    )
    return tmp_path / "bundle"


def test_cli_reports_summary_and_copies_bundle(tmp_path: Path, capsys) -> None:
    bundle_root = export_bundle(tmp_path)
    destination = tmp_path / "restored"

    exit_code = import_project_bundle.main(
        [
            "--bundle-root",
            str(bundle_root),
            "--destination-root",
            str(destination),
        ]
    )

    assert exit_code == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured["asset_count"] == 1
    assert captured["pattern_count"] == 1
    assert captured["manifest_sha256"]
    assert (destination / "project_manifest.json").exists()
    assert (destination / "assets" / "choir.wav").exists()
