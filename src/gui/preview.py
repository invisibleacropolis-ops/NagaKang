"""Preview orchestration glue that feeds the Step 7 GUI layout."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

from audio.tracker_bridge import PatternPlayback
from tracker.pattern_editor import PlaybackRequest
from tracker.playback_worker import PlaybackWorker, PreviewRender

from .mixer_board import MixerBoardAdapter, MixerStripState
from .state import MixerPanelState, TrackerMixerLayoutState, TrackerPanelState

LoudnessProvider = Callable[[PatternPlayback, float], List[Dict[str, object]]]


@dataclass
class PreviewBatchState:
    """Container bundling the layout state with the raw preview renders."""

    layout: TrackerMixerLayoutState
    previews: List[PreviewRender]


class PreviewOrchestrator:
    """Polls the playback worker and emits layout-ready state bundles."""

    def __init__(
        self,
        worker: PlaybackWorker,
        *,
        mixer_adapter: MixerBoardAdapter,
        beats_per_bucket: float = 1.0,
        loudness_provider: LoudnessProvider | None = None,
    ) -> None:
        if beats_per_bucket <= 0.0:
            raise ValueError("beats_per_bucket must be positive")
        self._worker = worker
        self._adapter = mixer_adapter
        self._beats_per_bucket = float(beats_per_bucket)
        self._loudness_provider = loudness_provider

    @property
    def beats_per_bucket(self) -> float:
        return self._beats_per_bucket

    def process_pending(self) -> PreviewBatchState:
        requests = self._worker.process_pending()
        previews = self._worker.last_render_batch()
        tracker_state = self._tracker_state(requests, previews)
        mixer_state = self._mixer_state()
        layout = TrackerMixerLayoutState(tracker=tracker_state, mixer=mixer_state)
        return PreviewBatchState(layout=layout, previews=previews)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _tracker_state(
        self,
        requests: Sequence[PlaybackRequest],
        previews: Sequence[PreviewRender],
    ) -> TrackerPanelState:
        pending = [self._worker.describe_request(req) for req in requests]
        summary = previews[-1].to_summary() if previews else None
        loudness_rows: List[Dict[str, object]] = []
        if previews and self._loudness_provider is not None:
            playback = previews[-1].playback
            loudness_rows = self._loudness_provider(playback, self._beats_per_bucket)
        pattern_id = self._worker.editor.pattern.id
        return TrackerPanelState(
            pattern_id=pattern_id,
            pending_requests=pending,
            last_preview_summary=summary,
            loudness_rows=loudness_rows,
        )

    def _mixer_state(self) -> MixerPanelState:
        strip_states: Dict[str, MixerStripState] = {}
        for name in self._adapter.channel_names():
            strip_states[name] = self._adapter.strip_state(name)
        return_states: Dict[str, MixerStripState] = {}
        for name in self._adapter.return_names():
            return_states[name] = self._adapter.return_state(name)
        master_meter = self._adapter.master_meter()
        return MixerPanelState(
            strip_states=strip_states,
            return_states=return_states,
            master_meter=master_meter,
        )
