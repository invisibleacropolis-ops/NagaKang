"""Tracker panel widgets and controllers for the Step 7 GUI shell."""
from __future__ import annotations

import math
import uuid
from typing import List

from domain.models import PatternStep
from tracker.pattern_editor import PatternEditor, PlaybackRequest, StepMutation
from tracker.preview_service import MutationPreviewService

from .state import TrackerPanelState

try:  # pragma: no cover - optional dependency for GUI runtimes
    from kivy.properties import (
        BooleanProperty,
        DictProperty,
        ListProperty,
        NumericProperty,
        StringProperty,
    )
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

    def BooleanProperty(default: bool = False):  # type: ignore
        return bool(default)


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


class TransportControlsWidget(BoxLayout):
    """Transport control strip binding transport/tutorial state into widgets."""

    tempo_bpm = NumericProperty(120.0)
    is_playing = BooleanProperty(False)
    loop_window_steps = NumericProperty(16.0)
    tutorial_tips = ListProperty([])
    onboarding_hint = StringProperty("")
    tutorial_tip_index = NumericProperty(0)
    recovery_prompt = StringProperty("")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._controller: TrackerPanelController | None = None

    def bind_controller(self, controller: "TrackerPanelController") -> None:
        self._controller = controller

    def apply_state(self, state: TrackerPanelState) -> None:
        self.tempo_bpm = float(state.tempo_bpm)
        self.is_playing = bool(state.is_playing)
        self.loop_window_steps = float(state.loop_window_steps)
        incoming_tips = list(state.tutorial_tips)
        previous_tips = list(self.tutorial_tips)
        self.tutorial_tips = incoming_tips
        if incoming_tips != previous_tips:
            self.tutorial_tip_index = 0
        self._sync_onboarding_hint()
        prompt = state.autosave_recovery_prompt or ""
        self.recovery_prompt = prompt

    def start_playback(
        self,
        *,
        start_step: int = 0,
        window_steps: float | None = None,
    ) -> List[PlaybackRequest]:
        if self._controller is None:
            return []
        if window_steps is None:
            window_steps = self.loop_window_steps
        if window_steps <= 0:
            raise ValueError("window_steps must be positive")
        requests = self._controller.preview_loop(
            start_step=start_step,
            window_steps=window_steps,
        )
        if requests:
            self.is_playing = True
        return requests

    def stop_playback(self) -> None:
        if self._controller is None:
            return
        self._controller.stop_preview()
        self.is_playing = False

    def set_loop_window_steps(self, steps: float) -> float:
        """Utility helper for slider bindings that clamps loop window input."""

        if steps <= 0:
            raise ValueError("loop window must be positive")
        self.loop_window_steps = float(steps)
        return self.loop_window_steps

    def advance_tutorial_hint(self) -> str:
        """Rotate through Step 1 onboarding tips for annotated demos."""

        tips = list(self.tutorial_tips)
        if not tips:
            self.onboarding_hint = ""
            return self.onboarding_hint
        self.tutorial_tip_index = (int(self.tutorial_tip_index) + 1) % len(tips)
        self._sync_onboarding_hint()
        return self.onboarding_hint

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _sync_onboarding_hint(self) -> None:
        tips = list(self.tutorial_tips)
        if not tips:
            self.onboarding_hint = ""
            return
        index = int(self.tutorial_tip_index) % len(tips)
        self.onboarding_hint = tips[index]


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

    def preview_loop(
        self,
        *,
        start_step: int = 0,
        window_steps: float | None = None,
    ) -> List[PlaybackRequest]:
        pattern = self.editor.pattern
        total_steps = pattern.length_steps
        if window_steps is None:
            window_steps = total_steps - start_step
        if window_steps is None or window_steps <= 0:
            raise ValueError("window_steps must be positive")
        start_index = max(0, int(start_step))
        end_index = min(total_steps, start_index + int(math.ceil(window_steps)))
        requests: List[PlaybackRequest] = []
        for index in range(start_index, end_index):
            step = self._copy_step(index)
            if step.note is None:
                continue
            mutation = StepMutation(
                mutation_id=f"loop_{uuid.uuid4().hex}",
                index=index,
                previous=step,
                updated=step,
            )
            start = self.editor.step_to_beat(index)
            duration = self.editor.steps_to_beats(1.0)
            requests.append(
                self._service.enqueue_mutation(
                    mutation,
                    start_beat=start,
                    step_duration_beats=duration,
                )
            )
        return requests

    def stop_preview(self) -> None:
        self._service.queue.clear()

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
    "TransportControlsWidget",
    "TrackerPanelController",
]
