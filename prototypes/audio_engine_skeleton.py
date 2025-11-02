"""Prototype audio engine skeleton for Step 2 validation.

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
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

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


@dataclass
class AudioMetrics:
    processed_blocks: int = 0
    underruns: int = 0
    callbacks: int = 0
    start_time: float = field(default_factory=time.perf_counter)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start_time


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

    def render(self, frames: int) -> "np.ndarray":
        if np is None:
            raise RuntimeError("NumPy is required for DSP rendering in this prototype.")

        if self.settings.test_tone_hz is None:
            return np.zeros((frames, self.settings.channels), dtype=np.float32)

        t = np.arange(frames, dtype=np.float32)
        freq = float(self.settings.test_tone_hz)
        increment = 2 * np.pi * freq / self.settings.sample_rate
        phase = self.phase + t * increment
        self.phase = float((phase[-1] + increment) % (2 * np.pi))
        tone = np.sin(phase, dtype=np.float32)
        return np.tile(tone[:, None], (1, self.settings.channels))


class AudioEngine:
    def __init__(self, settings: Optional[AudioSettings] = None) -> None:
        self.settings = settings or AudioSettings()
        self.dispatcher = EventDispatcher()
        self.graph = ModuleGraph(self.settings)
        self.metrics = AudioMetrics()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None

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
        logger.debug("Audio engine stopped after %s seconds", self.metrics.elapsed)

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

    def _on_audio_callback(self, frames: int, outdata=None):
        self.dispatcher.poll()
        if np is None:
            return None
        buffer = self.graph.render(frames)
        if outdata is not None:
            outdata[:] = buffer
        self.metrics.processed_blocks += 1
        self.metrics.callbacks += 1
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
        "Processed %s blocks in %.3f seconds (callbacks=%s, underruns=%s)",
        engine.metrics.processed_blocks,
        engine.metrics.elapsed,
        engine.metrics.callbacks,
        engine.metrics.underruns,
    )


if __name__ == "__main__":  # pragma: no cover - manual execution only
    main()
