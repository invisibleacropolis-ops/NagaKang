"""CLI entry point for :class:`domain.project_import_service.ProjectImportService`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from domain.project_import_service import ProjectImportService


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally copy an exported tracker project bundle.",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        required=True,
        help="Directory containing project_manifest.json and associated assets.",
    )
    parser.add_argument(
        "--destination-root",
        type=Path,
        help="Optional directory that will receive a copy of the validated bundle.",
    )
    parser.add_argument(
        "--manifest-name",
        default="project_manifest.json",
        help="Override the manifest filename when validating specialized bundles.",
    )
    parser.add_argument(
        "--project-name",
        default="project.json",
        help="Override the serialized project filename when exporting custom demos.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    service = ProjectImportService()
    bundle_root = args.bundle_root.expanduser().resolve()
    destination_root = args.destination_root
    if destination_root is not None:
        destination_root = destination_root.expanduser().resolve()

    result = service.import_bundle(
        bundle_root,
        destination_root=destination_root,
        manifest_filename=args.manifest_name,
        project_filename=args.project_name,
    )

    summary = {
        "bundle_root": str(bundle_root),
        "destination_root": str(destination_root) if destination_root else None,
        "manifest_sha256": result.manifest_sha256,
        "pattern_count": len(result.patterns),
        "snapshot_count": len(result.mixer_snapshots),
        "asset_count": len(result.sampler_assets),
        "asset_names": result.asset_names,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
