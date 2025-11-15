"""Kivy application shell that binds the preview orchestrator to widgets."""
from __future__ import annotations

from typing import Any

from .mixer_board import MixerDockController, MixerDockWidget
from .preview import PreviewBatchState, PreviewOrchestrator
from .state import TrackerMixerLayoutState
from .tracker_panel import (
    LoudnessTableWidget,
    TrackerGridWidget,
    TrackerPanelController,
    TransportControlsWidget,
)

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
        def __init__(self, **kwargs) -> None:
            self.children = []
            self.orientation = kwargs.get("orientation", "horizontal")

        def add_widget(self, widget) -> None:  # pragma: no cover - stub helper
            self.children.append(widget)


class TrackerMixerRoot(BoxLayout):
    """Top-level widget that polls the orchestrator and exposes layout state."""

    layout_state = ObjectProperty(None)
    tracker_grid = ObjectProperty(None)
    loudness_table = ObjectProperty(None)
    transport_controls = ObjectProperty(None)
    mixer_dock = ObjectProperty(None)
    tracker_column = ObjectProperty(None)

    def __init__(
        self,
        tracker_controller: TrackerPanelController | None = None,
        mixer_controller: MixerDockController | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._orchestrator: PreviewOrchestrator | None = None
        self._clock_event = None
        self._tracker_controller: TrackerPanelController | None = None
        self._mixer_controller: MixerDockController | None = None
        self._build_default_children()
        if tracker_controller is not None:
            self.bind_tracker_controller(tracker_controller)
        if mixer_controller is not None:
            self.bind_mixer_controller(mixer_controller)

    def _build_default_children(self) -> None:
        """Instantiate tracker-side widgets so demos run without KV layouts."""

        if getattr(self, "orientation", None) is None:
            self.orientation = "horizontal"
        self.tracker_column = BoxLayout(orientation="vertical")
        self.transport_controls = TransportControlsWidget()
        self.tracker_grid = TrackerGridWidget()
        self.loudness_table = LoudnessTableWidget()
        for widget in (self.transport_controls, self.tracker_grid, self.loudness_table):
            if hasattr(self.tracker_column, "add_widget"):
                self.tracker_column.add_widget(widget)
        self.mixer_dock = MixerDockWidget()
        self.add_widget(self.tracker_column)
        self.add_widget(self.mixer_dock)

    def bind_tracker_controller(self, controller: TrackerPanelController) -> None:
        """Wire controller gestures into the tracker widgets."""

        self._tracker_controller = controller
        if self.transport_controls is not None:
            self.transport_controls.bind_controller(controller)
        if self.tracker_grid is not None:
            self.tracker_grid.bind_controller(controller)

    def bind_mixer_controller(self, controller: MixerDockController) -> None:
        """Expose mixer dock gestures to an adapter-aware controller."""

        self._mixer_controller = controller
        if self.mixer_dock is not None:
            self.mixer_dock.bind_controller(controller)

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
        tracker_state = batch.layout.tracker
        if self.transport_controls is not None:
            self.transport_controls.apply_state(tracker_state)
        if self.tracker_grid is not None:
            self.tracker_grid.apply_state(tracker_state)
        if self.loudness_table is not None:
            self.loudness_table.apply_state(tracker_state)
        if self.mixer_dock is not None:
            self.mixer_dock.apply_state(batch.layout.mixer)


class TrackerMixerApp(App):
    """Minimal App wrapper suitable for instrumentation and manual demos."""

    def __init__(
        self,
        orchestrator: PreviewOrchestrator,
        *,
        tracker_controller: TrackerPanelController | None = None,
        mixer_controller: MixerDockController | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._orchestrator = orchestrator
        self._tracker_controller = tracker_controller
        self._mixer_controller = mixer_controller

    def build(self) -> TrackerMixerRoot:
        root = TrackerMixerRoot(
            tracker_controller=self._tracker_controller,
            mixer_controller=self._mixer_controller,
        )
        root.bind_orchestrator(self._orchestrator)
        return root

    def latest_layout(self) -> TrackerMixerLayoutState | None:
        root = getattr(self, "root", None)
        return getattr(root, "layout_state", None)
