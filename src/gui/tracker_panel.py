"""Tracker panel widgets and controllers for the Step 7 GUI shell."""
from __future__ import annotations

import uuid

from domain.models import PatternStep
from tracker.pattern_editor import PatternEditor, PlaybackRequest, StepMutation
from tracker.preview_service import MutationPreviewService

from .state import TrackerPanelState

try:  # pragma: no cover - optional dependency for GUI runtimes
    from kivy.properties import DictProperty, ListProperty, NumericProperty, StringProperty
    from kivy.uix.boxlayout import BoxLayout
except Exception:  # pragma: no cover - fallback for headless CI and docs builds
    class BoxLayout:  # type: ignore
        def __init__(self, **_kwargs) -> None:
            super().__init__()

    def DictProperty(default=None):  # type: ignore
        return {} if default is None else dict(default)

    def ListProperty(default=None):  # type: ignore
        return list(default or [])

    def NumericProperty(default: float = 0.0):  # type: ignore
        return float(default)

    def StringProperty(default: str = ""):
        return default


class TrackerGridWidget(BoxLayout):
    """Minimal tracker grid widget that reacts to :class:`TrackerPanelState`."""

    pattern_id = StringProperty("--")
    pending_requests = ListProperty([])
    last_preview_summary = DictProperty({})
    selected_step = NumericProperty(-1)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._controller: TrackerPanelController | None = None

    def bind_controller(self, controller: "TrackerPanelController") -> None:
        self._controller = controller

    def apply_state(self, state: TrackerPanelState) -> None:
        self.pattern_id = state.pattern_id
        self.pending_requests = list(state.pending_requests)
        self.last_preview_summary = dict(state.last_preview_summary or {})

    def select_step(self, index: int) -> None:
        self.selected_step = int(index)
        if self._controller is not None:
            self._controller.preview_step(index)


class LoudnessTableWidget(BoxLayout):
    """Widget that renders loudness rows for rehearsal dashboards."""

    loudness_rows = ListProperty([])
    pattern_id = StringProperty("--")

    def apply_state(self, state: TrackerPanelState) -> None:
        self.pattern_id = state.pattern_id
        self.loudness_rows = list(state.loudness_rows)


class TrackerPanelController:
    """Bridges tracker gestures to preview queue mutations."""

    def __init__(
        self,
        preview_service: MutationPreviewService,
        *,
        selection_window_steps: float = 1.0,
    ) -> None:
        if selection_window_steps <= 0:
            raise ValueError("selection_window_steps must be positive")
        self._service = preview_service
        self._selection_window_steps = float(selection_window_steps)

    @property
    def editor(self) -> PatternEditor:
        return self._service.editor

    def preview_step(self, index: int) -> PlaybackRequest:
        step = self._copy_step(index)
        mutation = StepMutation(
            mutation_id=f"selection_{uuid.uuid4().hex}",
            index=index,
            previous=step,
            updated=step,
        )
        start = self.editor.step_to_beat(index)
        duration = self.editor.steps_to_beats(self._selection_window_steps)
        return self._service.enqueue_mutation(
            mutation,
            start_beat=start,
            step_duration_beats=duration,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _copy_step(self, index: int) -> PatternStep:
        pattern = self.editor.pattern
        if index < 0 or index >= len(pattern.steps):
            raise IndexError("Step index out of range")
        return pattern.steps[index].model_copy()


__all__ = [
    "TrackerGridWidget",
    "LoudnessTableWidget",
    "TrackerPanelController",
]
