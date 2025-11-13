"""Kivy application shell that binds the preview orchestrator to widgets."""
from __future__ import annotations

from typing import Any

from .preview import PreviewBatchState, PreviewOrchestrator
from .state import TrackerMixerLayoutState

try:  # pragma: no cover - optional dependency for headless CI
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.properties import ObjectProperty
    from kivy.uix.boxlayout import BoxLayout
except Exception:  # pragma: no cover - fallback for non-GUI environments
    class App:  # type: ignore
        def __init__(self, **_kwargs) -> None:
            pass

        def build(self) -> Any:  # pragma: no cover - stub
            return None

    class Clock:  # type: ignore
        @staticmethod
        def schedule_interval(callback, _interval):  # pragma: no cover - stub
            return None

    def ObjectProperty(default=None):  # type: ignore
        return default

    class BoxLayout:  # type: ignore
        def __init__(self, **_kwargs) -> None:
            pass


class TrackerMixerRoot(BoxLayout):
    """Top-level widget that polls the orchestrator and exposes layout state."""

    layout_state = ObjectProperty(None)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orchestrator: PreviewOrchestrator | None = None
        self._clock_event = None

    def bind_orchestrator(self, orchestrator: PreviewOrchestrator, *, interval: float = 0.5) -> None:
        self._orchestrator = orchestrator
        if hasattr(Clock, "schedule_interval"):
            self._clock_event = Clock.schedule_interval(self._poll_orchestrator, interval)

    def _poll_orchestrator(self, *_args) -> None:
        if self._orchestrator is None:
            return
        batch = self._orchestrator.process_pending()
        self._apply_batch(batch)

    def _apply_batch(self, batch: PreviewBatchState) -> None:
        self.layout_state = batch.layout


class TrackerMixerApp(App):
    """Minimal App wrapper suitable for instrumentation and manual demos."""

    def __init__(self, orchestrator: PreviewOrchestrator, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orchestrator = orchestrator

    def build(self) -> TrackerMixerRoot:
        root = TrackerMixerRoot()
        root.bind_orchestrator(self._orchestrator)
        return root

    def latest_layout(self) -> TrackerMixerLayoutState | None:
        root = getattr(self, "root", None)
        return getattr(root, "layout_state", None)
