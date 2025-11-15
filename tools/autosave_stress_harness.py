"""Exercise Tracker/Mixer autosave checkpoints under synthetic preview loads."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from domain.project_manifest import SamplerManifestIndex
from gui.app import TrackerMixerRoot
from gui.preview import PreviewBatchState
from gui.state import MixerPanelState, TrackerMixerLayoutState, TrackerPanelState


@dataclass
class _TimeSource:
    interval: float
    current: float = 0.0

    def advance(self) -> None:
        self.current += self.interval

    def __call__(self) -> float:
        return self.current


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a synthetic autosave workload and report checkpoint metrics.",
    )
    parser.add_argument("--project-id", required=True, help="Project identifier used for .autosave folder names.")
    parser.add_argument(
        "--autosave-dir",
        type=Path,
        required=True,
        help="Directory that will store .autosave/<project_id> checkpoints.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=8,
        help="Number of preview batches to process during the drill.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0.5,
        help="Synthetic time delta applied between autosave attempts.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional project manifest copied next to autosave checkpoints for crash drills.",
    )
    parser.add_argument(
        "--asset-count",
        type=int,
        default=0,
        help="Expected sampler asset count surfaced to the tracker UI state.",
    )
    return parser.parse_args(argv)


def _load_manifest(path: Path | None) -> SamplerManifestIndex | None:
    if path is None:
        return None
    resolved = Path(path)
    if not resolved.exists():
        raise SystemExit(f"Manifest '{resolved}' does not exist")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return SamplerManifestIndex.from_payload(payload)


def run_harness(args: argparse.Namespace) -> dict[str, object]:
    manifest_index = _load_manifest(args.manifest)
    root = TrackerMixerRoot()
    if manifest_index is not None:
        root.configure_sampler_manifest(manifest_index, manifest_path=args.manifest)
    time_source = _TimeSource(interval=float(args.interval_seconds))
    root.enable_autosave(
        project_id=args.project_id,
        autosave_dir=args.autosave_dir,
        interval_seconds=args.interval_seconds,
        time_source=time_source,
    )

    start = time.perf_counter()
    for iteration in range(int(args.iterations)):
        time_source.advance()
        tracker_state = TrackerPanelState(
            pattern_id=f"demo_{iteration}",
            import_asset_count=int(args.asset_count),
            tutorial_tips=["Autosave ready"],
        )
        layout = TrackerMixerLayoutState(tracker=tracker_state, mixer=MixerPanelState())
        batch = PreviewBatchState(layout=layout, previews=[])
        root._apply_batch(batch)
    duration = time.perf_counter() - start
    config = root._autosave_config
    checkpoints = config.checkpoints if config is not None else []

    return {
        "iterations": int(args.iterations),
        "checkpoints_written": len(checkpoints),
        "pruned_checkpoints": getattr(config, "pruned_checkpoints", 0) if config else 0,
        "latest_prompt": root.transport_controls.recovery_prompt if root.transport_controls else "",
        "duration_seconds": duration,
        "autosave_dir": str(args.autosave_dir / args.project_id),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_harness(args)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
