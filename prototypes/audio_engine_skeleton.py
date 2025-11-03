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
import heapq
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import numpy as np
except ImportError:  # pragma: no cover - fallback
    np = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import sounddevice as sd
except ImportError:  # pragma: no cover - fallback
    sd = None  # type: ignore


@dataclass
class AudioSettings:
    sample_rate: int = 48_000
    block_size: int = 512
    channels: int = 2
    test_tone_hz: Optional[float] = None


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the audio engine skeleton prototype")
    parser.add_argument("--duration", type=float, default=1.0, help="How long to run the engine (seconds)")
    parser.add_argument("--tone", type=float, default=None, help="Optional test tone frequency in Hz")
    parser.add_argument("--sample-rate", type=int, default=48_000, help="Sample rate in Hz")
    parser.add_argument("--block-size", type=int, default=512, help="Frames per callback")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args()
    settings = AudioSettings(
        sample_rate=args.sample_rate,
        block_size=args.block_size,
        test_tone_hz=args.tone,
    )
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
