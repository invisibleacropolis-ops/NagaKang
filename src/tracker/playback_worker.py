"""Playback worker prototype that drains preview requests for Step 4."""
from __future__ import annotations

from collections.abc import Callable
from typing import Dict, List

from .pattern_editor import PatternEditor, PlaybackRequest
from .preview_service import MutationPreviewService


class PlaybackWorker:
    """Lightweight worker that processes queued preview playback requests."""

    def __init__(
        self,
        service: MutationPreviewService,
        *,
        on_request: Callable[[PlaybackRequest], None] | None = None,
    ) -> None:
        self._service = service
        self._callbacks: List[Callable[[PlaybackRequest], None]] = []
        if on_request is not None:
            self._callbacks.append(on_request)
        self._processed: List[PlaybackRequest] = []

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

    def process_pending(self) -> List[PlaybackRequest]:
        """Drain pending preview requests and invoke registered callbacks."""

        requests = self._service.drain_requests()
        for request in requests:
            for callback in self._callbacks:
                callback(request)
        self._processed.extend(requests)
        return requests

    def processed_requests(self) -> List[PlaybackRequest]:
        """Return a copy of the processed request history."""

        return list(self._processed)

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


__all__ = ["PlaybackWorker"]
