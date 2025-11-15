"""CI helper that captures mixer diagnostics summaries with trend metadata."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Iterable, Mapping, MutableSequence

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:  # pragma: no cover - import guard for tooling
    sys.path.insert(0, str(SRC_PATH))

from audio.engine import EngineConfig

if str(ROOT) not in sys.path:  # pragma: no cover - tools import helper
    sys.path.insert(0, str(ROOT))

from tools import mixer_diagnostics


def capture_summary(duration: float, blocks: int | None, demo_automation: bool) -> Mapping[str, object]:
    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    graph = mixer_diagnostics._build_demo_graph(config)
    if demo_automation:
        mixer_diagnostics._schedule_demo_automation(graph, duration)
    mixer_diagnostics._render_graph(graph, duration, blocks)
    return mixer_diagnostics._build_summary(graph)


def build_markdown(summary: Mapping[str, object], diff: Mapping[str, object] | None, label: str) -> str:
    master = summary.get("master_meter", {})
    peak = master.get("peak_db", "--")
    rms = master.get("rms_db", "--")
    lines = ["# Mixer Trend Snapshot", ""]
    lines.append(f"Label: **{label or 'ci-capture'}**")
    lines.append(f"Master bus: peak {peak} dBFS / RMS {rms} dBFS")
    lines.append("")
    lines.append("## Stored artifacts")
    lines.append("- JSON summary: included alongside CI artifacts")
    lines.append("- Audio render pointers: see `docs/assets/audio/sampler_s3_manifest.json`")
    if diff:
        lines.append("")
        lines.append("## Meter deltas vs. baseline")
        channel_deltas = diff.get("channel_post_meters", {})
        for name, payload in channel_deltas.items():
            peak_delta = payload.get("peak_delta_db")
            rms_delta = payload.get("rms_delta_db")
            status = payload.get("status")
            if status:
                lines.append(f"- {name}: {status}")
                continue
            lines.append(
                "- {name}: Δpeak={peak} dB | Δrms={rms} dB".format(
                    name=name,
                    peak=f"{peak_delta:.2f}" if peak_delta is not None else "--",
                    rms=f"{rms_delta:.2f}" if rms_delta is not None else "--",
                )
            )
    return "\n".join(lines) + "\n"


def append_history(
    entry: Mapping[str, object],
    history_json: Path | None,
    history_markdown: Path | None,
) -> None:
    if history_json is not None:
        existing: MutableSequence[Mapping[str, object]] = []
        if history_json.exists():
            existing = json.loads(history_json.read_text())
        existing.append(entry)
        history_json.parent.mkdir(parents=True, exist_ok=True)
        history_json.write_text(json.dumps(existing, indent=2))
    if history_markdown is not None:
        lines = []
        if history_markdown.exists():
            lines = history_markdown.read_text().splitlines()
        else:
            lines = ["# Mixer Trend History", ""]
        timestamp = entry.get("timestamp")
        label = entry.get("label")
        master = entry.get("master_meter", {})
        lines.append(f"- {timestamp} – {label}: peak {master.get('peak_db', '--')} dBFS / RMS {master.get('rms_db', '--')} dBFS")
        history_markdown.parent.mkdir(parents=True, exist_ok=True)
        history_markdown.write_text("\n".join(lines) + "\n")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--history-json", type=Path)
    parser.add_argument("--history-markdown", type=Path)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--blocks", type=int)
    parser.add_argument("--demo-automation", action="store_true")
    parser.add_argument("--label", type=str, default="ci-capture")
    parser.add_argument("--write-baseline", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    duration = max(args.duration, 0.05)
    summary = capture_summary(duration, args.blocks, args.demo_automation)
    baseline_data = None
    diff = None
    if args.baseline_json.exists():
        baseline_data = json.loads(args.baseline_json.read_text())
        diff = mixer_diagnostics._build_diff(baseline_data, summary)
        summary = dict(summary)
        summary["diff"] = diff
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "label": args.label,
        "master_meter": summary.get("master_meter", {}),
    }
    if diff is not None:
        entry["channel_post_meters"] = diff.get("channel_post_meters", {})
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2))
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(build_markdown(summary, diff, args.label))
    append_history(entry, args.history_json, args.history_markdown)
    if args.write_baseline:
        args.baseline_json.parent.mkdir(parents=True, exist_ok=True)
        args.baseline_json.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
