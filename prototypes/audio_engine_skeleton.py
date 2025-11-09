"""Prototype audio engine skeleton for Step 2 validation with richer metrics.

This module focuses on mapping the architecture decisions from
`docs/step2_architecture_tech_choices.md` into executable scaffolding.
It intentionally avoids complex DSP so that we can validate threading
and data flow before committing to heavy optimizations.

Usage:
    python prototypes/audio_engine_skeleton.py --duration 2.0

The prototype attempts to stream silence (or a test tone) through the
configured backend. If the optional `sounddevice` dependency is not
available, the engine falls back to an in-memory ring buffer and logs
simulated callbacks so the control flow can still be exercised during
tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import heapq
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import numpy as np
except ImportError:  # pragma: no cover - fallback
    np = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import sounddevice as sd
except ImportError:  # pragma: no cover - fallback
    sd = None  # type: ignore

from audio.engine import (
    AutomationTimeline as MusicianAutomationTimeline,
    BaseAudioModule as MusicianBaseModule,
    EngineConfig as MusicianEngineConfig,
    OfflineAudioEngine as MusicianOfflineEngine,
    ParameterSpec as MusicianParameterSpec,
    TempoMap as MusicianTempoMap,
)
from audio.metrics import integrated_lufs as musician_integrated_lufs
from audio.metrics import rms_dbfs as musician_rms_dbfs
from audio.modules import AmplitudeEnvelope, OnePoleLowPass, SineOscillator
from audio.tracker_bridge import PatternPerformanceBridge
from tracker import MutationPreviewService, PatternEditor, PlaybackWorker


@dataclass
class AudioSettings:
    sample_rate: int = 48_000
    block_size: int = 512
    channels: int = 2
    test_tone_hz: Optional[float] = None
    tempo_bpm: float = 120.0


@dataclass(order=True)
class AutomationEvent:
    """Deferred parameter change executed on a buffer boundary."""

    time_seconds: float
    parameter: str = field(compare=False)
    value: float = field(compare=False)


@dataclass
class AudioMetrics:
    processed_blocks: int = 0
    underruns: int = 0
    callbacks: int = 0
    start_time: float = field(default_factory=time.perf_counter)
    engine_time: float = 0.0
    last_callback_duration: float = 0.0
    max_callback_duration: float = 0.0
    _callback_durations: List[float] = field(default_factory=list)
    _cpu_load_observations: List[float] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start_time

    def record_callback(self, duration: float, block_duration: float) -> None:
        """Capture timing metadata for a single callback."""

        self.last_callback_duration = duration
        if duration > self.max_callback_duration:
            self.max_callback_duration = duration
        self._callback_durations.append(duration)
        if block_duration > 0.0:
            self._cpu_load_observations.append(duration / block_duration)

    @property
    def average_callback_duration(self) -> float:
        if not self._callback_durations:
            return 0.0
        return float(sum(self._callback_durations) / len(self._callback_durations))

    @property
    def callback_duration_p95(self) -> float:
        if not self._callback_durations:
            return 0.0
        sorted_values = sorted(self._callback_durations)
        index = int(round(0.95 * (len(sorted_values) - 1)))
        return float(sorted_values[index])

    @property
    def average_cpu_load(self) -> float:
        if not self._cpu_load_observations:
            return 0.0
        return float(sum(self._cpu_load_observations) / len(self._cpu_load_observations))

    @property
    def max_cpu_load(self) -> float:
        if not self._cpu_load_observations:
            return 0.0
        return float(max(self._cpu_load_observations))

    def snapshot(self) -> dict[str, float]:
        """Return aggregate metrics useful for benchmark tables."""

        return {
            "processed_blocks": float(self.processed_blocks),
            "underruns": float(self.underruns),
            "callbacks": float(self.callbacks),
            "avg_callback_ms": self.average_callback_duration * 1_000.0,
            "p95_callback_ms": self.callback_duration_p95 * 1_000.0,
            "avg_cpu_load": self.average_cpu_load,
            "max_cpu_load": self.max_cpu_load,
        }


@dataclass
class StressTestScenario:
    """Configuration bundle describing a single stress harness execution."""

    name: str
    duration_seconds: float
    processing_overhead: float
    settings: AudioSettings

    def metadata(self) -> dict[str, object]:
        """Return static metadata describing the scenario for exports."""

        return {
            "scenario": self.name,
            "duration_seconds": float(self.duration_seconds),
            "processing_overhead_seconds": float(self.processing_overhead),
            "sample_rate": self.settings.sample_rate,
            "block_size": self.settings.block_size,
            "channels": self.settings.channels,
            "test_tone_hz": self.settings.test_tone_hz,
        }


class EventDispatcher:
    """Minimal dispatcher interface to mirror architectural decisions."""

    def __init__(self) -> None:
        self._event_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

    def schedule(self, event: Callable[[], None]) -> None:
        logger.debug("Scheduling event %s", event)
        self._event_queue.put(event)

    def poll(self, budget: int = 32) -> None:
        for _ in range(budget):
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            logger.debug("Executing event %s", event)
            event()


class ModuleGraph:
    """Placeholder graph that produces silence or a simple sine tone."""

    def __init__(self, settings: AudioSettings) -> None:
        self.settings = settings
        self.phase = 0.0
        self.parameters: dict[str, Optional[float]] = {"test_tone_hz": settings.test_tone_hz}

    def set_parameter(self, name: str, value: Optional[float]) -> None:
        logger.debug("Setting parameter %s=%s", name, value)
        self.parameters[name] = value

    def get_parameter(self, name: str) -> Optional[float]:
        return self.parameters.get(name)

    def render(self, frames: int) -> "np.ndarray":
        if np is None:
            raise RuntimeError("NumPy is required for DSP rendering in this prototype.")

        freq = self.get_parameter("test_tone_hz")
        if freq is None:
            return np.zeros((frames, self.settings.channels), dtype=np.float32)

        t = np.arange(frames, dtype=np.float32)
        increment = 2 * np.pi * float(freq) / self.settings.sample_rate
        phase = self.phase + t * increment
        self.phase = float((phase[-1] + increment) % (2 * np.pi))
        tone = np.sin(phase, dtype=np.float32)
        return np.tile(tone[:, None], (1, self.settings.channels))


class _ModuleGraphAdapter(MusicianBaseModule):
    """Bridge ModuleGraph into the musician-focused OfflineAudioEngine."""

    def __init__(self, graph: ModuleGraph, config: MusicianEngineConfig) -> None:
        super().__init__(
            "prototype_graph",
            config,
            [
                MusicianParameterSpec(
                    name="test_tone_hz",
                    display_name="Test Tone",
                    default=graph.get_parameter("test_tone_hz"),
                    minimum=0.0,
                    maximum=20_000.0,
                    unit="Hz",
                    description="Reference tone routed through the prototype graph.",
                    musical_context="pitch",
                    allow_none=True,
                )
            ],
        )
        self._graph = graph

    def set_parameter(self, name: str, value: float | None) -> None:  # type: ignore[override]
        super().set_parameter(name, value)
        if name == "test_tone_hz":
            self._graph.set_parameter(name, value if value is not None else None)

    def get_parameter(self, name: str) -> float | None:  # type: ignore[override]
        if name == "test_tone_hz":
            return self._graph.get_parameter(name)
        return super().get_parameter(name)

    def process(self, frames: int) -> "np.ndarray":
        return self._graph.render(frames)


class AudioEngine:
    def __init__(
        self,
        settings: Optional[AudioSettings] = None,
        *,
        processing_overhead: float = 0.0,
    ) -> None:
        self.settings = settings or AudioSettings()
        self.dispatcher = EventDispatcher()
        self.graph = ModuleGraph(self.settings)
        self.metrics = AudioMetrics()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._automation_events: List[AutomationEvent] = []
        self._automation_lock = threading.Lock()
        self.processing_overhead = processing_overhead

    def start(self) -> None:
        if self._running.is_set():
            return
        logger.debug("Starting audio engine with settings %s", self.settings)
        self._running.set()
        if sd is not None:
            self._start_sounddevice_stream()
        else:
            self._thread = threading.Thread(target=self._simulate_callback_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.debug(
            "Audio engine stopped after %.3f seconds (processed_blocks=%s)",
            self.metrics.elapsed,
            self.metrics.processed_blocks,
        )

    def schedule_parameter_automation(
        self, parameter: str, value: Optional[float], time_seconds: float
    ) -> None:
        """Schedule a parameter change to align with the realtime timeline."""

        with self._automation_lock:
            heapq.heappush(self._automation_events, AutomationEvent(time_seconds, parameter, value))

    def render_offline(self, duration_seconds: float) -> "np.ndarray":
        """Render buffers without starting realtime threads for CI usage."""

        if np is None:
            raise RuntimeError("NumPy is required for offline rendering.")

        total_frames = max(0, int(round(duration_seconds * self.settings.sample_rate)))
        if total_frames == 0:
            return np.zeros((0, self.settings.channels), dtype=np.float32)

        buffers = []
        remaining = total_frames
        while remaining > 0:
            frames = min(remaining, self.settings.block_size)
            buffers.append(self._on_audio_callback(frames))
            remaining -= frames
        return np.vstack(buffers)

    def render_with_musician_engine(
        self,
        duration_seconds: float,
        *,
        beat_automation: Optional[Sequence[tuple[float, Optional[float]]]] = None,
    ) -> "np.ndarray":
        """Render using the production OfflineAudioEngine with beat automation."""

        if np is None:
            raise RuntimeError("NumPy is required for offline rendering.")

        config = MusicianEngineConfig(
            sample_rate=self.settings.sample_rate,
            block_size=self.settings.block_size,
            channels=self.settings.channels,
        )
        tempo = MusicianTempoMap(tempo_bpm=self.settings.tempo_bpm)
        timeline = MusicianAutomationTimeline()
        engine = MusicianOfflineEngine(config, tempo=tempo, timeline=timeline)
        adapter = _ModuleGraphAdapter(self.graph, config)
        engine.add_module(adapter, as_output=True)

        if beat_automation is not None:
            for beats, value in beat_automation:
                engine.schedule_parameter_change(
                    module=adapter.name,
                    parameter="test_tone_hz",
                    beats=beats,
                    value=value,
                    source="prototype beat automation",
                )

        buffer = engine.render(duration_seconds)
        self.metrics.engine_time += duration_seconds
        return buffer

    def run_stress_test(
        self, duration_seconds: float, *, processing_overhead: Optional[float] = None
    ) -> AudioMetrics:
        """Execute an offline run while simulating callback pressure.

        Args:
            duration_seconds: Total duration to render offline.
            processing_overhead: Optional override for artificial per-callback
                sleep duration used to emulate heavy DSP load. When omitted the
                instance-level ``processing_overhead`` value is reused.

        Returns:
            A reference to :class:`AudioMetrics` capturing underruns and
            callback durations observed during the run. Metrics are cumulative
            so callers may inspect deltas relative to prior snapshots.
        """

        previous = self.processing_overhead
        try:
            if processing_overhead is not None:
                self.processing_overhead = processing_overhead
            self.render_offline(duration_seconds)
            return self.metrics
        finally:
            self.processing_overhead = previous

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _start_sounddevice_stream(self) -> None:  # pragma: no cover - requires audio device
        if sd is None:
            return

        def callback(outdata, frames, time_info, status):
            self._on_audio_callback(frames, outdata)

        stream = sd.OutputStream(
            samplerate=self.settings.sample_rate,
            blocksize=self.settings.block_size,
            channels=self.settings.channels,
            dtype="float32",
            callback=callback,
        )
        stream.start()
        self._thread = threading.Thread(target=self._wait_for_stop, args=(stream,), daemon=True)
        self._thread.start()

    def _simulate_callback_loop(self) -> None:
        logger.debug("Running simulated callback loop")
        frame_duration = self.settings.block_size / self.settings.sample_rate
        while self._running.is_set():
            buffer = None
            if np is not None:
                buffer = self._on_audio_callback(self.settings.block_size)
                logger.debug("Simulated buffer shape: %s", None if buffer is None else buffer.shape)
            else:
                self.metrics.underruns += 1
                logger.warning("NumPy missing; unable to render buffer")
            time.sleep(frame_duration)

    def _wait_for_stop(self, stream):  # pragma: no cover - requires audio device
        try:
            while self._running.is_set():
                time.sleep(0.1)
        finally:
            stream.stop()
            stream.close()

    def _drain_automation_events(self, start: float, end: float) -> None:
        with self._automation_lock:
            while self._automation_events and self._automation_events[0].time_seconds <= end:
                event = heapq.heappop(self._automation_events)
                if event.time_seconds < start:
                    logger.debug("Applying late automation event %s at %s", event, start)
                self.graph.set_parameter(event.parameter, event.value)

    def _on_audio_callback(self, frames: int, outdata=None):
        self.dispatcher.poll()
        if np is None:
            return None

        block_duration = frames / self.settings.sample_rate
        start_engine_time = self.metrics.engine_time
        self._drain_automation_events(start_engine_time, start_engine_time + block_duration)

        start_time = time.perf_counter()
        buffer = self.graph.render(frames)
        if self.processing_overhead > 0.0:
            time.sleep(self.processing_overhead)
        duration = time.perf_counter() - start_time

        if outdata is not None:
            outdata[:] = buffer

        self.metrics.record_callback(duration, block_duration)
        if duration > block_duration:
            self.metrics.underruns += 1
        self.metrics.processed_blocks += 1
        self.metrics.callbacks += 1
        self.metrics.engine_time += block_duration
        return buffer


def _build_result_record(
    scenario: StressTestScenario, snapshot: dict[str, float]
) -> dict[str, object]:
    record = scenario.metadata()
    record.update(
        {
            "processed_blocks": int(round(snapshot["processed_blocks"])),
            "underruns": int(round(snapshot["underruns"])),
            "callbacks": int(round(snapshot["callbacks"])),
            "avg_callback_ms": snapshot["avg_callback_ms"],
            "p95_callback_ms": snapshot["p95_callback_ms"],
            "avg_cpu_load": snapshot["avg_cpu_load"],
            "max_cpu_load": snapshot["max_cpu_load"],
        }
    )
    return record


def run_stress_test_scenarios(
    scenarios: Sequence[StressTestScenario],
    *,
    csv_path: Path | None = None,
    json_path: Path | None = None,
) -> list[dict[str, object]]:
    """Execute multiple stress-test scenarios and optionally export artifacts."""

    results: list[dict[str, object]] = []
    for scenario in scenarios:
        engine = AudioEngine(settings=scenario.settings)
        metrics = engine.run_stress_test(
            scenario.duration_seconds, processing_overhead=scenario.processing_overhead
        )
        results.append(_build_result_record(scenario, metrics.snapshot()))

    if csv_path is not None and results:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(results[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)

    return results


def load_stress_plan(path: Path) -> list[StressTestScenario]:
    """Load a JSON plan describing stress harness scenarios."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Stress plan must be a JSON array of scenario objects")

    scenarios: list[StressTestScenario] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("Each scenario must be a JSON object")

        try:
            name = str(entry["name"])
            duration = float(entry["duration_seconds"])
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise ValueError("Scenario missing required keys 'name' or 'duration_seconds'") from exc

        processing_overhead = float(entry.get("processing_overhead_seconds", 0.0))
        settings_payload = entry.get("settings", {})
        if not isinstance(settings_payload, dict):
            raise ValueError("Scenario 'settings' must be an object")

        settings = AudioSettings(
            sample_rate=int(settings_payload.get("sample_rate", AudioSettings.sample_rate)),
            block_size=int(settings_payload.get("block_size", AudioSettings.block_size)),
            channels=int(settings_payload.get("channels", AudioSettings.channels)),
            test_tone_hz=(
                float(settings_payload["test_tone_hz"]) if "test_tone_hz" in settings_payload else None
            ),
            tempo_bpm=float(settings_payload.get("tempo_bpm", AudioSettings.tempo_bpm)),
        )
        scenarios.append(
            StressTestScenario(
                name=name,
                duration_seconds=duration,
                processing_overhead=processing_overhead,
                settings=settings,
            )
        )

    return scenarios


def render_musician_demo_patch(settings: AudioSettings, duration_seconds: float) -> dict[str, float]:
    """Render a beat-synced tone demo and return headline loudness metrics."""

    if np is None:
        raise RuntimeError("NumPy is required for the musician demo render.")

    config = MusicianEngineConfig(
        sample_rate=settings.sample_rate,
        block_size=settings.block_size,
        channels=settings.channels,
    )
    engine = MusicianOfflineEngine(
        config,
        tempo=MusicianTempoMap(tempo_bpm=settings.tempo_bpm),
        timeline=MusicianAutomationTimeline(),
    )

    oscillator = SineOscillator("lead", config)
    envelope = AmplitudeEnvelope("lead_env", config, source=oscillator, attack_ms=35.0, release_ms=260.0)
    filter_module = OnePoleLowPass("lead_filter", config, source=envelope, cutoff_hz=3_500.0)

    engine.add_module(oscillator)
    engine.add_module(envelope)
    engine.add_module(filter_module, as_output=True)

    engine.schedule_parameter_change("lead", "amplitude", value=0.6, time_seconds=0.0)
    engine.schedule_parameter_change("lead_env", "gate", beats=0.0, value=1.0)
    engine.schedule_parameter_change("lead_env", "gate", beats=4.0, value=0.0)
    engine.schedule_parameter_change("lead_filter", "cutoff_hz", beats=0.0, value=2_000.0)
    engine.schedule_parameter_change("lead_filter", "cutoff_hz", beats=2.0, value=6_000.0)
    engine.schedule_parameter_change("lead_filter", "cutoff_hz", beats=3.5, value=1_500.0)

    buffer = engine.render(duration_seconds)
    loudness = musician_rms_dbfs(buffer)
    lufs = musician_integrated_lufs(buffer, sample_rate=config.sample_rate)
    return {
        "rms_left_dbfs": float(loudness[0]),
        "rms_right_dbfs": float(loudness[-1]),
        "integrated_lufs": float(lufs),
        "duration_seconds": float(duration_seconds),
    }


def _build_demo_tracker_bridge(settings: AudioSettings) -> tuple[PatternPerformanceBridge, "InstrumentDefinition"]:
    """Return a demo PatternPerformanceBridge plus sampler instrument for tracker previews."""

    if np is None:
        raise RuntimeError("NumPy is required for the tracker demos.")

    from domain.models import InstrumentDefinition, InstrumentModule

    config = MusicianEngineConfig(
        sample_rate=settings.sample_rate,
        block_size=settings.block_size,
        channels=settings.channels,
    )
    tempo = MusicianTempoMap(tempo_bpm=settings.tempo_bpm)

    duration_seconds = 0.75
    frames = int(duration_seconds * settings.sample_rate)
    time_axis = np.linspace(0.0, duration_seconds, frames, endpoint=False, dtype=np.float32)
    base = np.sin(2.0 * np.pi * 180.0 * time_axis, dtype=np.float32)
    bright = np.sin(2.0 * np.pi * 360.0 * time_axis, dtype=np.float32)
    fade = np.linspace(1.0, 0.2, frames, dtype=np.float32)
    sample = np.stack([base * fade, bright * fade], axis=1)

    instrument = InstrumentDefinition(
        id="demo_sampler",
        name="Demo Clip",
        modules=[
            InstrumentModule(
                id="sampler",
                type="clip_sampler:demo",
                parameters={
                    "start_percent": 0.1,
                    "length_percent": 0.5,
                    "amplitude": 0.85,
                },
            ),
            InstrumentModule(
                id="env",
                type="amplitude_envelope",
                parameters={"attack_ms": 18.0, "release_ms": 140.0},
                inputs=["sampler"],
            ),
            InstrumentModule(
                id="filter",
                type="one_pole_low_pass",
                parameters={"cutoff_hz": 2_800.0},
                inputs=["env"],
            ),
        ],
    )

    bridge = PatternPerformanceBridge(config, tempo, sample_library={"demo": sample})
    return bridge, instrument



def render_pattern_bridge_demo(settings: AudioSettings) -> dict[str, object]:
    """Render a tracker-style pattern through the sampler bridge and summarise loudness."""

    if np is None:
        raise RuntimeError("NumPy is required for the pattern bridge demo render.")

    from domain.models import AutomationPoint, Pattern, PatternStep

    bridge, instrument = _build_demo_tracker_bridge(settings)

    pattern = Pattern(
        id="demo_pattern",
        name="Demo Pattern",
        length_steps=16,
        steps=[
            PatternStep(note=60, velocity=100, instrument_id=instrument.id),
            PatternStep(),
            PatternStep(
                note=67,
                velocity=112,
                instrument_id=instrument.id,
                step_effects={"length_beats": 0.75},
            ),
            *[PatternStep() for _ in range(13)],
        ],
        automation={
            "filter.cutoff_hz|smooth=6ms:5": [
                AutomationPoint(position_beats=0.0, value=1_800.0),
                AutomationPoint(position_beats=2.0, value=4_800.0),
            ]
        },
    )

    playback = bridge.render_pattern(pattern, instrument)
    loudness = bridge.loudness_trends(playback, beats_per_bucket=1.0)
    smoothing_rows = bridge.automation_smoothing_rows(playback)
    smoothing_total = sum(
        int(row.get("segment_total") or row.get("segments") or 0)
        for row in smoothing_rows
        if isinstance(row, dict)
    )
    return {
        "duration_seconds": playback.duration_seconds,
        "beat_loudness": loudness,
        "automation_events": playback.automation_log,
        "automation_smoothing": smoothing_rows,
        "automation_smoothing_summary": {
            "rows": len(smoothing_rows),
            "segment_total": smoothing_total,
        },
    }

def run_tracker_preview_demo(settings: AudioSettings) -> dict[str, object]:
    """Exercise the tracker preview worker with MutationPreviewService."""

    if np is None:
        raise RuntimeError("NumPy is required for the tracker preview demo render.")

    from domain.models import Pattern, PatternStep

    bridge, instrument = _build_demo_tracker_bridge(settings)

    pattern = Pattern(
        id="preview_pattern",
        name="Preview Pattern",
        length_steps=16,
        steps=[PatternStep() for _ in range(16)],
    )

    editor = PatternEditor(pattern, steps_per_beat=6.0)
    service = MutationPreviewService(editor)
    request_summaries: List[dict[str, object]] = []
    render_summaries: List[dict[str, object]] = []

    worker = PlaybackWorker(
        service,
        bridge=bridge,
        instruments={instrument.id: instrument},
        default_instrument_id=instrument.id,
    )
    worker.add_callback(lambda request: request_summaries.append(worker.describe_request(request)))
    worker.add_render_callback(lambda preview: render_summaries.append(preview.to_summary()))

    with service.preview_batch("paint chord"):
        editor.set_step(0, note=60, velocity=100, instrument_id=instrument.id)
        editor.apply_effect(0, "length_beats", 1.5)
        editor.set_step(6, note=64, velocity=108, instrument_id=instrument.id)
        editor.set_step(9, note=67, velocity=112, instrument_id=instrument.id)

    worker.process_pending()

    editor.set_step(12, note=72, velocity=120, instrument_id=instrument.id)
    service.enqueue_mutation(editor.history[-1])
    worker.process_pending()

    return {
        "mutations": len(editor.history),
        "preview_requests": request_summaries,
        "preview_renders": render_summaries,
        "steps_per_beat": editor.steps_per_beat,
        "engine_sample_rate": bridge.config.sample_rate,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the audio engine skeleton prototype")
    parser.add_argument("--duration", type=float, default=1.0, help="How long to run the engine (seconds)")
    parser.add_argument("--tone", type=float, default=None, help="Optional test tone frequency in Hz")
    parser.add_argument("--sample-rate", type=int, default=48_000, help="Sample rate in Hz")
    parser.add_argument("--block-size", type=int, default=512, help="Frames per callback")
    parser.add_argument("--tempo", type=float, default=120.0, help="Tempo in BPM for beat automation")
    parser.add_argument(
        "--stress-plan",
        type=Path,
        help="JSON file describing offline stress-test scenarios to execute",
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        help="Destination path for JSON summary (stress plans or demos)",
    )
    parser.add_argument(
        "--export-csv",
        type=Path,
        help="Destination path for stress-test CSV summary (requires --stress-plan)",
    )
    parser.add_argument(
        "--musician-demo",
        action="store_true",
        help="Render the Step 3 musician demo patch and print loudness metrics",
    )
    parser.add_argument(
        "--pattern-demo",
        action="store_true",
        help="Render the tracker pattern bridge demo and print beat loudness snapshots",
    )
    parser.add_argument(
        "--tracker-preview-demo",
        action="store_true",
        help="Queue tracker preview requests via the Step 4 playback worker",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args()

    if args.stress_plan is not None:
        scenarios = load_stress_plan(args.stress_plan)
        results = run_stress_test_scenarios(
            scenarios, csv_path=args.export_csv, json_path=args.export_json
        )
        for record in results:
            logger.info(
                "Scenario %s: callbacks=%s underruns=%s avg=%.4fms p95=%.4fms cpu=%.3f/%.3f",
                record["scenario"],
                record["callbacks"],
                record["underruns"],
                record["avg_callback_ms"],
                record["p95_callback_ms"],
                record["avg_cpu_load"],
                record["max_cpu_load"],
            )
        return

    settings = AudioSettings(
        sample_rate=args.sample_rate,
        block_size=args.block_size,
        test_tone_hz=args.tone,
        tempo_bpm=args.tempo,
    )

    if args.musician_demo:
        metrics = render_musician_demo_patch(settings, args.duration)
        logger.info(
            "Musician demo render: %.2f s, RMS L/R %.2f/%.2f dBFS, integrated %.2f LUFS",
            metrics["duration_seconds"],
            metrics["rms_left_dbfs"],
            metrics["rms_right_dbfs"],
            metrics["integrated_lufs"],
        )
        return
    if args.pattern_demo:
        summary = render_pattern_bridge_demo(settings)
        for bucket in summary["beat_loudness"]:
            logger.info(
                "Pattern beats %.1f–%.1f: RMS L/R %.2f/%.2f dBFS, %.2f LUFS",
                bucket["start_beat"],
                bucket["end_beat"],
                bucket["rms_left_dbfs"],
                bucket["rms_right_dbfs"],
                bucket["integrated_lufs"],
            )
        logger.info(
            "Pattern demo automation events: %s", len(summary["automation_events"])  # type: ignore[index]
        )
        smoothing_rows = summary.get("automation_smoothing", [])  # type: ignore[index]
        if smoothing_rows:
            total_segments = 0
            for row in smoothing_rows:
                if not isinstance(row, dict):
                    continue
                event_id = str(row.get("event_id") or row.get("identifier"))
                window_beats = float(row.get("window_beats", 0.0) or 0.0)
                state = "applied" if row.get("applied") else "pending"
                segment_total = int(row.get("segment_total") or row.get("segments") or 0)
                total_segments += max(0, segment_total)
                breakdown = row.get("segment_breakdown")
                if isinstance(breakdown, dict) and breakdown:
                    parts = ", ".join(f"{name}={value}" for name, value in breakdown.items())
                    segment_copy = f"{segment_total} total ({parts})"
                else:
                    segment_copy = f"{segment_total} total"
                logger.info(
                    "Smoothing %s: %s segments over %.2f beats (%s)",
                    event_id,
                    segment_copy,
                    window_beats,
                    state,
                )
            summary_row = summary.get("automation_smoothing_summary", {})  # type: ignore[index]
            rows = summary_row.get("rows", len(smoothing_rows))
            segments = summary_row.get("segment_total", total_segments)
            logger.info("Smoothing summary: %s rows, %s segments", rows, segments)
        if args.export_json:
            payload = {
                "demo": "pattern",
                **summary,
            }
            args.export_json.parent.mkdir(parents=True, exist_ok=True)
            args.export_json.write_text(json.dumps(payload, indent=2, sort_keys=True))
            logger.info("Wrote pattern demo summary to %s", args.export_json)
        return
    if args.tracker_preview_demo:
        preview = run_tracker_preview_demo(settings)
        logger.info(
            "Tracker preview demo: %s mutations queued %s requests and %s renders (resolution %.2f steps/beat, %s Hz)",
            preview["mutations"],
            len(preview["preview_requests"]),
            len(preview.get("preview_renders", [])),
            preview["steps_per_beat"],
            preview.get("engine_sample_rate", settings.sample_rate),
        )
        for request in preview["preview_requests"]:
            logger.info(
                "Preview %s @ %.2f beats (%.2f beats) → steps %s-%s note=%s vel=%s instrument=%s",
                request["mutation_id"],
                request["start_beat"],
                request["duration_beats"],
                request["start_step"],
                request["end_step"],
                request["note"],
                request["velocity"],
                request["instrument_id"],
            )
        for render in preview.get("preview_renders", []):
            logger.info(
                "Render %s: %s frames (%.3f s) peak=%.3f rms=%.3f",
                render.get("mutation_id"),
                render.get("window_frames"),
                render.get("window_seconds", 0.0),
                render.get("peak_amplitude", 0.0),
                render.get("rms_amplitude", 0.0),
            )
        return
    engine = AudioEngine(settings=settings)
    engine.start()
    time.sleep(max(0.0, args.duration))
    engine.stop()
    logger.info(
        "Processed %s blocks in %.3f seconds (callbacks=%s, underruns=%s, max_cb=%.4fs)",
        engine.metrics.processed_blocks,
        engine.metrics.elapsed,
        engine.metrics.callbacks,
        engine.metrics.underruns,
        engine.metrics.max_callback_duration,
    )


if __name__ == "__main__":  # pragma: no cover - manual execution only
    main()
