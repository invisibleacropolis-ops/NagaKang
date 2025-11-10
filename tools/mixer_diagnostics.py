#!/usr/bin/env python3
"""Mixer diagnostics CLI exposing Step 6 metering and automation hooks.

Run with ``poetry run python tools/mixer_diagnostics.py`` to process a short
mixing pass using the demo graph from the Step 6 documentation.  The command
prints subgroup meter readings alongside any scheduled automation events so QA
runs can confirm mixer routing without launching the GUI.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Mapping

import numpy as np

from audio.effects import PlateReverbInsert, StereoFeedbackDelayInsert
from audio.engine import EngineConfig
from audio.mixer import (
    MeterReading,
    MixerChannel,
    MixerGraph,
    MixerReturnBus,
    MixerSendConfig,
    MixerSubgroup,
)


@dataclass
class ConstantModule:
    """Simple source used to feed deterministic levels into the mixer graph."""

    name: str
    config: EngineConfig
    value: float

    def process(self, frames: int) -> np.ndarray:  # pragma: no cover - CLI helper
        return np.full((frames, self.config.channels), self.value, dtype=np.float32)


def _build_demo_graph(config: EngineConfig) -> MixerGraph:
    graph = MixerGraph(config)

    drums = MixerSubgroup("drums", config=config, fader_db=-3.0)
    band = MixerSubgroup("band", config=config)
    graph.add_subgroup(drums)
    graph.add_subgroup(band)
    graph.assign_subgroup_to_group("drums", "band")

    drum_bus = MixerReturnBus(
        "drum_room",
        processor=PlateReverbInsert(config, mix=0.45, decay=0.65),
        level_db=-4.0,
    )
    vox_delay = MixerReturnBus(
        "vox_delay",
        processor=StereoFeedbackDelayInsert(config, delay_ms=180.0, feedback=0.35),
        level_db=-9.0,
    )
    graph.add_return_bus(drum_bus)
    graph.add_return_bus(vox_delay)

    kick_src = ConstantModule("kick_src", config, value=0.75)
    vox_src = ConstantModule("vox_src", config, value=0.55)

    kick = MixerChannel(
        "Kick",
        source=kick_src,
        config=config,
        sends=[MixerSendConfig(bus="drum_room", level_db=-8.0, pre_fader=True)],
    )
    vox = MixerChannel(
        "Vocals",
        source=vox_src,
        config=config,
        sends=[
            MixerSendConfig(bus="drum_room", level_db=-24.0),
            MixerSendConfig(bus="vox_delay", level_db=-15.0),
        ],
    )
    graph.add_channel(kick)
    graph.add_channel(vox)
    graph.assign_channel_to_group("Kick", "drums")
    graph.assign_channel_to_group("Vocals", "band")

    return graph


def _schedule_demo_automation(graph: MixerGraph, duration: float) -> None:
    """Demonstrate send/subgroup automation for CLI output."""

    graph.schedule_parameter_change(
        "mixer:subgroup:band",
        "fader_db",
        value=-3.0,
        time_seconds=0.0,
        source="cli_demo",
    )
    graph.schedule_parameter_change(
        "mixer:subgroup:band",
        "fader_db",
        value=0.0,
        time_seconds=max(duration - 0.1, 0.0),
        source="cli_demo",
    )
    graph.schedule_parameter_change(
        "mixer:channel:Vocals",
        "send:vox_delay",
        value=-6.0,
        time_seconds=duration / 2.0,
        source="cli_demo",
    )


def _render_graph(graph: MixerGraph, duration: float, blocks: int | None) -> None:
    config = graph.config
    if blocks is not None:
        total_frames = max(1, blocks) * config.block_size
        remaining = total_frames
        while remaining > 0:
            frames = min(config.block_size, remaining)
            graph.process_block(frames)
            remaining -= frames
    else:
        graph.render(duration)


def _meters_snapshot(meters: Mapping[str, MeterReading]) -> Dict[str, Dict[str, float]]:
    snapshot: Dict[str, Dict[str, float]] = {}
    for name, meter in meters.items():
        snapshot[name] = {"peak_db": meter.peak_db, "rms_db": meter.rms_db}
    return snapshot


def _automation_snapshot(events: List) -> List[Dict[str, object]]:
    snapshot: List[Dict[str, object]] = []
    for event in events:
        payload = asdict(event)
        snapshot.append(payload)
    return snapshot


def _build_summary(graph: MixerGraph) -> Dict[str, object]:
    return {
        "channel_groups": dict(graph.channel_groups),
        "subgroup_meters": _meters_snapshot(graph.subgroup_meters),
        "automation_events": _automation_snapshot(graph.automation_events),
        "return_levels": {
            name: bus.level_db for name, bus in graph.returns.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Render duration in seconds when --blocks is not provided.",
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=None,
        help="Number of mixer blocks to process (overrides --duration).",
    )
    parser.add_argument(
        "--demo-automation",
        action="store_true",
        help="Schedule example automation events before rendering.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable summary.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (implies --json).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    graph = _build_demo_graph(config)
    duration = max(args.duration, 0.05)
    if args.demo_automation:
        _schedule_demo_automation(graph, duration)
    _render_graph(graph, duration, args.blocks)
    summary = _build_summary(graph)

    if args.json or args.pretty:
        print(json.dumps(summary, indent=2 if args.pretty else None))
    else:
        print("Mixer Diagnostics Summary")
        print("==========================")
        print("Channel ➜ Subgroup assignments:")
        for channel, subgroup in summary["channel_groups"].items():
            print(f"  - {channel} → {subgroup}")
        print("\nSubgroup meters (peak / RMS):")
        for name, meter in summary["subgroup_meters"].items():
            peak = meter["peak_db"]
            rms = meter["rms_db"]
            print(f"  - {name}: {peak:.2f} dBFS / {rms:.2f} dBFS")
        if summary["automation_events"]:
            print("\nScheduled automation events:")
            for event in summary["automation_events"]:
                module = event["module"]
                parameter = event["parameter"]
                time_seconds = event["time_seconds"]
                value = event.get("value")
                source = event.get("source", "")
                print(
                    f"  - {time_seconds:.3f}s {module}.{parameter} → {value}"
                    + (f" ({source})" if source else "")
                )
        else:
            print("\nNo automation events scheduled.")
        print("\nReturn bus levels:")
        for name, level in summary["return_levels"].items():
            print(f"  - {name}: {level:.2f} dB")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
