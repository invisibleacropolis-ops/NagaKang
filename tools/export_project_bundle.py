"""CLI helper that bundles tracker projects plus manifests for QA drills."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Sequence

from domain.models import Project
from domain.project_export_service import (
    MixerSnapshotSpec,
    ProjectExportService,
    SamplerAssetSpec,
)
from domain.project_manifest import SamplerManifestIndex

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLER_MANIFEST = PROJECT_ROOT / "docs" / "assets" / "audio" / "sampler_s3_manifest.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export tracker projects, mixer snapshots, and sampler assets into a portable bundle.",
    )
    parser.add_argument(
        "--project-file",
        type=Path,
        required=True,
        help="Path to the serialized project JSON document.",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        required=True,
        help="Destination directory that will contain the exported bundle.",
    )
    parser.add_argument(
        "--sampler-manifest",
        type=Path,
        default=DEFAULT_SAMPLER_MANIFEST,
        help="Sampler manifest JSON used to validate asset hashes.",
    )
    parser.add_argument(
        "--mixer-snapshot",
        action="append",
        default=[],
        metavar="NAME=PATH[,TYPE]",
        help=(
            "Mixer snapshot specification. Provide a label and the JSON path plus an optional type "
            "(channel, subgroup, master)."
        ),
    )
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        metavar="ASSET_NAME=SOURCE_PATH",
        help="Sampler asset to copy into the bundle while validating checksums via the manifest.",
    )
    parser.add_argument(
        "--skip-project-json",
        action="store_true",
        help="Avoid writing project.json next to the manifest (useful for manifest-only drills).",
    )
    return parser.parse_args(argv)


def _load_project(path: Path) -> Project:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Project.model_validate(payload)


def _parse_snapshot_specs(entries: Iterable[str]) -> list[MixerSnapshotSpec]:
    specs: list[MixerSnapshotSpec] = []
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(
                f"Invalid --mixer-snapshot entry '{entry}'. Expected NAME=PATH[,TYPE]."
            )
        name, _, remainder = entry.partition("=")
        path_part, _, type_part = remainder.partition(",")
        snapshot_path = Path(path_part).expanduser().resolve()
        snapshot_type = type_part or "channel"
        specs.append(
            MixerSnapshotSpec(
                name=name.strip(),
                path=snapshot_path,
                snapshot_type=snapshot_type.strip() or "channel",
            )
        )
    return specs


def _parse_asset_specs(entries: Iterable[str]) -> list[SamplerAssetSpec]:
    specs: list[SamplerAssetSpec] = []
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"Invalid --asset entry '{entry}'. Expected NAME=PATH.")
        asset_name, _, source_str = entry.partition("=")
        specs.append(
            SamplerAssetSpec(
                asset_name=asset_name.strip(),
                source_path=Path(source_str).expanduser().resolve(),
            )
        )
    return specs


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_file = args.project_file.expanduser().resolve()
    if not project_file.exists():
        raise SystemExit(f"Project file '{project_file}' does not exist.")

    project = _load_project(project_file)
    bundle_root = args.bundle_root.expanduser().resolve()

    sampler_manifest: SamplerManifestIndex | None = None
    asset_specs = _parse_asset_specs(args.asset)
    if asset_specs:
        manifest_path = args.sampler_manifest.expanduser().resolve()
        if not manifest_path.exists():
            raise SystemExit(
                "Sampler manifest is required for asset exports. "
                f"'{manifest_path}' was not found."
            )
        sampler_manifest = SamplerManifestIndex.from_file(manifest_path)

    snapshot_specs = _parse_snapshot_specs(args.mixer_snapshot)
    service = ProjectExportService(sampler_manifest=sampler_manifest)
    result = service.export_project(
        project,
        bundle_root=bundle_root,
        snapshot_specs=snapshot_specs,
        asset_specs=asset_specs,
        write_project_copy=not args.skip_project_json,
    )

    print(f"Exported manifest to {result.manifest_path}")
    print(f"Patterns: {len(result.pattern_paths)} | Snapshots: {len(result.mixer_snapshot_paths)} | Assets: {len(result.sampler_asset_paths)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
