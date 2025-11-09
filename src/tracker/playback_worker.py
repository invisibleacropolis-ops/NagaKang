"""Playback worker prototype that drains preview requests for Step 4."""
from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Dict, List

from .pattern_editor import PatternEditor, PlaybackRequest
from .preview_service import MutationPreviewService

if False:  # pragma: no cover - imported for type checking only
    from audio.tracker_bridge import PatternPlayback, PatternPerformanceBridge
    from domain.models import InstrumentDefinition
    import numpy as np


@dataclass
class PreviewRender:
    """Lightweight container describing a rendered preview window."""

    request: PlaybackRequest
    playback: "PatternPlayback"
    window_buffer: "np.ndarray"
    start_frame: int
    end_frame: int
    sample_rate: int

    @property
    def window_frames(self) -> int:
        """Return the number of frames captured for the preview window."""

        return max(0, self.end_frame - self.start_frame)

    @property
    def window_seconds(self) -> float:
        """Return the window duration in seconds."""

        if self.sample_rate <= 0:
            return 0.0
        return self.window_frames / float(self.sample_rate)

    def _window_stats(self) -> Dict[str, float]:
        """Compute basic amplitude metrics for the preview window."""

        try:  # pragma: no cover - exercised indirectly via higher-level tests
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is an optional dependency
            return {}

        buffer = self.window_buffer
        if buffer.size == 0:
            return {"peak_amplitude": 0.0, "rms_amplitude": 0.0}

        flattened = buffer.reshape(-1)
        peak = float(np.max(np.abs(flattened)))
        rms = float(math.sqrt(float(np.mean(np.square(flattened)))))
        return {"peak_amplitude": peak, "rms_amplitude": rms}

    def to_summary(self) -> Dict[str, object]:
        """Return a serialisable summary combining the request and render window."""

        summary: Dict[str, object] = {
            **asdict(self.request),
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "window_frames": self.window_frames,
            "window_seconds": self.window_seconds,
            "sample_rate": self.sample_rate,
        }
        summary.update(self._window_stats())
        return summary


class PlaybackWorker:
    """Lightweight worker that processes queued preview playback requests."""

    def __init__(
        self,
        service: MutationPreviewService,
        *,
        on_request: Callable[[PlaybackRequest], None] | None = None,
        bridge: "PatternPerformanceBridge" | None = None,
        instruments: Mapping[str, "InstrumentDefinition"] | None = None,
        default_instrument_id: str | None = None,
        instrument_resolver: Callable[[PlaybackRequest], "InstrumentDefinition | None"] | None = None,
        on_render: Callable[[PreviewRender], None] | None = None,
    ) -> None:
        self._service = service
        self._callbacks: List[Callable[[PlaybackRequest], None]] = []
        if on_request is not None:
            self._callbacks.append(on_request)
        self._bridge = bridge
        self._instruments = dict(instruments or {})
        self._default_instrument_id = default_instrument_id
        self._instrument_resolver = instrument_resolver
        self._render_callbacks: List[Callable[[PreviewRender], None]] = []
        if on_render is not None:
            self._render_callbacks.append(on_render)
        self._processed: List[PlaybackRequest] = []
        self._render_history: List[PreviewRender] = []
        self._last_render_batch: List[PreviewRender] = []

    @property
    def service(self) -> MutationPreviewService:
        """Return the wrapped preview service."""

        return self._service

    @property
    def editor(self) -> PatternEditor:
        """Return the underlying pattern editor driving preview scheduling."""

        return self._service.editor

    def add_callback(self, callback: Callable[[PlaybackRequest], None]) -> None:
        """Register a function invoked for every processed request."""

        self._callbacks.append(callback)

    def add_render_callback(self, callback: Callable[[PreviewRender], None]) -> None:
        """Register a function invoked for every rendered preview window."""

        self._render_callbacks.append(callback)

    def process_pending(self) -> List[PlaybackRequest]:
        """Drain pending preview requests and invoke registered callbacks."""

        requests = self._service.drain_requests()
        renders: List[PreviewRender] = []
        playback_cache: Dict[str, "PatternPlayback"] = {}
        for request in requests:
            for callback in self._callbacks:
                callback(request)
            preview = self._render_request(request, playback_cache)
            if preview is not None:
                renders.append(preview)
                for render_callback in self._render_callbacks:
                    render_callback(preview)
        self._processed.extend(requests)
        if renders:
            self._render_history.extend(renders)
        self._last_render_batch = renders
        return requests

    def processed_requests(self) -> List[PlaybackRequest]:
        """Return a copy of the processed request history."""

        return list(self._processed)

    def preview_history(self) -> List[PreviewRender]:
        """Return a copy of the rendered preview history."""

        return list(self._render_history)

    def last_render_batch(self) -> List[PreviewRender]:
        """Return the previews generated during the most recent processing call."""

        return list(self._last_render_batch)

    async def process_pending_async(self) -> List[PlaybackRequest]:
        """Asynchronously drain pending preview requests.

        The coroutine mirrors :meth:`process_pending` but offloads the draining
        work to a worker thread. This keeps UI threads responsive while still
        allowing synchronous render callbacks to execute.
        """

        return await asyncio.to_thread(self.process_pending)

    def describe_request(self, request: PlaybackRequest) -> Dict[str, object]:
        """Return a tracker-oriented summary for logging or CLI demos."""

        start_step, end_step = self.editor.beat_window_to_step_range(
            request.start_beat, request.duration_beats
        )
        return {
            "mutation_id": request.mutation_id,
            "index": request.index,
            "start_beat": request.start_beat,
            "duration_beats": request.duration_beats,
            "start_step": start_step,
            "end_step": end_step,
            "note": request.note,
            "velocity": request.velocity,
            "instrument_id": request.instrument_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_instrument(self, request: PlaybackRequest) -> "InstrumentDefinition | None":
        instrument: "InstrumentDefinition | None" = None
        if self._instrument_resolver is not None:
            instrument = self._instrument_resolver(request)

        if instrument is None:
            instrument_id = request.instrument_id or self._default_instrument_id
            if instrument_id is not None:
                instrument = self._instruments.get(instrument_id)
        return instrument

    def _render_request(
        self,
        request: PlaybackRequest,
        playback_cache: Dict[str, "PatternPlayback"] | None = None,
    ) -> PreviewRender | None:
        if self._bridge is None:
            return None

        instrument = self._resolve_instrument(request)
        if instrument is None:
            return None

        try:
            import numpy as np
        except ImportError:  # pragma: no cover - optional dependency guard
            return None

        cache_key = instrument.id
        playback: "PatternPlayback" | None = None
        if playback_cache is not None:
            playback = playback_cache.get(cache_key)

        if playback is None:
            playback = self._bridge.render_pattern(self.editor.pattern, instrument)
            if playback_cache is not None:
                playback_cache[cache_key] = playback

        sample_rate = int(self._bridge.config.sample_rate)
        total_frames = playback.buffer.shape[0]
        start_seconds = self._bridge.tempo.beats_to_seconds(max(0.0, request.start_beat))
        duration_seconds = self._bridge.tempo.beats_to_seconds(max(0.0, request.duration_beats))

        start_frame = max(0, int(math.floor(start_seconds * sample_rate)))
        if duration_seconds <= 0.0:
            end_frame = min(total_frames, start_frame + 1)
        else:
            span_frames = int(math.ceil(duration_seconds * sample_rate))
            end_frame = min(total_frames, max(start_frame + 1, start_frame + span_frames))

        window_buffer = playback.buffer[start_frame:end_frame].copy()
        return PreviewRender(
            request=request,
            playback=playback,
            window_buffer=window_buffer,
            start_frame=start_frame,
            end_frame=end_frame,
            sample_rate=sample_rate,
        )


__all__ = ["PlaybackWorker", "PreviewRender"]
