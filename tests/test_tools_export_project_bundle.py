from pathlib import Path

import pytest

from domain.models import Pattern, PatternStep, Project, ProjectMetadata

from tools import export_project_bundle


def write_project(tmp_path: Path) -> Path:
    metadata = ProjectMetadata(id="cli-demo", name="CLI Demo")
    project = Project(metadata=metadata)
    pattern = Pattern(id="hook", name="Hook", length_steps=8, steps=[PatternStep() for _ in range(8)])
    project.add_pattern(pattern)
    project_file = tmp_path / "project.json"
    project_file.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return project_file


def write_sampler_manifest(tmp_path: Path, asset_path: Path) -> Path:
    payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {
                "name": asset_path.name,
                "sha256": "3957a235fae214722cb1521c7702aca6a4a6deefcbf5f7e221879662ed84cd4b",
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    import json as _json

    manifest_path.write_text(_json.dumps(payload, indent=2))
    return manifest_path


def test_cli_exports_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_file = write_project(tmp_path)
    bundle_root = tmp_path / "bundle"
    asset_source = tmp_path / "imports" / "choir.wav"
    asset_source.parent.mkdir(parents=True, exist_ok=True)
    asset_source.write_bytes(b"demo-bytes")
    manifest_path = write_sampler_manifest(tmp_path, asset_source)
    snapshot = tmp_path / "snapshots" / "hook.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{}", encoding="utf-8")

    args = [
        "--project-file",
        str(project_file),
        "--bundle-root",
        str(bundle_root),
        "--sampler-manifest",
        str(manifest_path),
        "--asset",
        f"{asset_source.name}={asset_source}",
        "--mixer-snapshot",
        f"Hook={snapshot},master",
    ]

    exit_code = export_project_bundle.main(args)
    assert exit_code == 0

    manifest_file = bundle_root / "project_manifest.json"
    assert manifest_file.exists()
    assert (bundle_root / "patterns" / "hook.json").exists()
    assert (bundle_root / "assets" / asset_source.name).exists()
