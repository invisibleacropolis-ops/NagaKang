"""Tests for the Step 8 project manifest schema and import helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from domain.models import Pattern, PatternStep, Project, ProjectMetadata
from domain.project_manifest import (
    ProjectManifestBuilder,
    SamplerManifestIndex,
    build_import_plan,
)


@pytest.fixture()
def demo_project() -> Project:
    metadata = ProjectMetadata(
        id="demo-project",
        name="Demo Project",
        created_at=datetime(2025, 11, 25, tzinfo=UTC),
        updated_at=datetime(2025, 11, 25, tzinfo=UTC),
        bpm=128.0,
        swing=0.12,
    )
    project = Project(metadata=metadata)
    pattern = Pattern(id="verse", name="Verse", length_steps=64, steps=[PatternStep()])
    project.add_pattern(pattern)
    return project


def _write_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_manifest_builder_collects_patterns_snapshots_and_assets(tmp_path: Path, demo_project: Project) -> None:
    builder = ProjectManifestBuilder(demo_project, base_path=tmp_path)
    pattern_path = _write_file(tmp_path / "patterns" / "verse.json", b"{}")
    builder.add_pattern_file("verse", pattern_path)
    snapshot_path = _write_file(tmp_path / "mixer" / "verse_snapshot.json", b"{\n  \"meters\": []\n}")
    builder.add_mixer_snapshot("Verse Snapshot", snapshot_path, snapshot_type="master")

    asset_bytes = b"choir-pad-soft"
    asset_path = _write_file(tmp_path / "imports" / "choir_pad_soft.wav", asset_bytes)
    manifest_payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {
                "name": "choir_pad_soft.wav",
                "nas_path": "NAS:/choir_pad_soft.wav",
                "s3_uri": "s3://demo/choir_pad_soft.wav",
                "lufs": -18.5,
                "peak_dbfs": -3.0,
                "sha256": "be347dd0d261695fce0b91c094da337b5ce6c5cee6b9947e1189e74224716072",
            }
        ],
    }
    manifest_index = SamplerManifestIndex.from_payload(manifest_payload)
    # Copy under an exports directory so the manifest stores relative paths.
    exports_root = tmp_path / "exports"
    record = manifest_index.copy_asset(
        asset_name="choir_pad_soft.wav",
        source_path=asset_path,
        destination_dir=exports_root / "assets",
        relative_to=exports_root,
    )
    builder.add_sampler_asset(record)

    manifest = builder.build()
    assert manifest.project.id == "demo-project"
    assert manifest.patterns[0].path == "patterns/verse.json"
    assert manifest.mixer_snapshots[0].snapshot_type == "master"
    assert manifest.sampler_assets[0].relative_path.startswith("assets/")


def test_copy_asset_rejects_checksum_mismatches(tmp_path: Path) -> None:
    bad_bytes = b"mismatched"
    asset_path = _write_file(tmp_path / "imports" / "asset.wav", bad_bytes)
    manifest_payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {
                "name": "asset.wav",
                "sha256": "cafecafe",
            }
        ],
    }
    manifest_index = SamplerManifestIndex.from_payload(manifest_payload)
    with pytest.raises(ValueError):
        manifest_index.copy_asset(
            asset_name="asset.wav",
            source_path=asset_path,
            destination_dir=tmp_path / "exports",
        )


def test_import_plan_surface_dialog_filters(tmp_path: Path) -> None:
    manifest_payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {"name": "choir.wav", "sha256": "aa"},
            {"name": "pad.flac", "sha256": "bb"},
        ],
    }
    manifest_index = SamplerManifestIndex.from_payload(manifest_payload)
    plan = build_import_plan(manifest_index)
    assert plan.asset_count == 2
    assert plan.dialog_filters[0]["label"] == "Sampler Assets"
    assert set(plan.dialog_filters[0]["patterns"]) == {"*.wav", "*.flac"}
