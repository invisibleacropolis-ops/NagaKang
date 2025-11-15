"""Kivy application shell that binds the preview orchestrator to widgets."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Deque, List

from domain.project_manifest import ProjectImportPlan, SamplerManifestIndex, build_import_plan

from .mixer_board import MixerDockController, MixerDockWidget
from .preview import PreviewBatchState, PreviewOrchestrator
from .state import TrackerMixerLayoutState, TrackerPanelState
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


@dataclass
class _AutosaveConfig:
    """Runtime configuration describing how autosave checkpoints behave."""

    project_id: str
    autosave_dir: Path
    interval_seconds: float = 90.0
    max_checkpoints: int = 5
    time_source: Callable[[], float] = time.monotonic
    manifest_path: Path | None = None
    last_saved: float | None = None
    checkpoints: Deque[tuple[Path, List[Path]]] = field(default_factory=deque)


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
        self._import_plan: ProjectImportPlan | None = None
        self._sampler_manifest: SamplerManifestIndex | None = None
        self._manifest_path: Path | None = None
        self._autosave_config: _AutosaveConfig | None = None

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

    def configure_sampler_manifest(
        self,
        manifest: SamplerManifestIndex,
        *,
        manifest_path: Path | None = None,
    ) -> None:
        """Capture sampler manifest metadata for import dialogs and autosave."""

        self._sampler_manifest = manifest
        self._import_plan = build_import_plan(manifest)
        if manifest_path is not None:
            self._manifest_path = Path(manifest_path)

    def enable_autosave(
        self,
        *,
        project_id: str,
        autosave_dir: Path,
        interval_seconds: float = 90.0,
        max_checkpoints: int = 5,
        manifest_path: Path | None = None,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        """Persist tracker state summaries plus manifests under `.autosave/`."""

        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if max_checkpoints <= 0:
            raise ValueError("max_checkpoints must be positive")
        autosave_dir = Path(autosave_dir)
        autosave_dir.mkdir(parents=True, exist_ok=True)
        manifest_override = manifest_path or self._manifest_path
        if manifest_override is not None:
            self._manifest_path = Path(manifest_override)
        self._autosave_config = _AutosaveConfig(
            project_id=project_id,
            autosave_dir=autosave_dir,
            interval_seconds=float(interval_seconds),
            max_checkpoints=int(max_checkpoints),
            manifest_path=self._manifest_path,
            time_source=time_source or time.monotonic,
        )

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
        self._apply_import_plan(tracker_state)
        if self.transport_controls is not None:
            self.transport_controls.apply_state(tracker_state)
        if self.tracker_grid is not None:
            self.tracker_grid.apply_state(tracker_state)
        if self.loudness_table is not None:
            self.loudness_table.apply_state(tracker_state)
        if self.mixer_dock is not None:
            self.mixer_dock.apply_state(batch.layout.mixer)
        self._maybe_autosave(batch)

    # ------------------------------------------------------------------
    # Autosave and import helpers
    # ------------------------------------------------------------------
    def _apply_import_plan(self, tracker_state: TrackerPanelState) -> None:
        if self._import_plan is None:
            return
        tracker_state.import_dialog_filters = list(self._import_plan.dialog_filters)
        tracker_state.import_asset_count = self._import_plan.asset_count

    def _maybe_autosave(self, batch: PreviewBatchState) -> None:
        config = self._autosave_config
        if config is None:
            return
        now = config.time_source()
        if config.last_saved is not None and now - config.last_saved < config.interval_seconds:
            return
        tracker_state = batch.layout.tracker
        checkpoint, attachments = self._write_autosave_checkpoint(config, tracker_state)
        config.last_saved = now
        config.checkpoints.append((checkpoint, attachments))
        while len(config.checkpoints) > config.max_checkpoints:
            layout_path, extras = config.checkpoints.popleft()
            layout_path.unlink(missing_ok=True)
            for extra in extras:
                extra.unlink(missing_ok=True)

    def _write_autosave_checkpoint(
        self,
        config: _AutosaveConfig,
        tracker_state: TrackerPanelState,
    ) -> tuple[Path, List[Path]]:
        target_dir = config.autosave_dir / config.project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC)
        slug = timestamp.strftime("%Y%m%d-%H%M%S")
        checkpoint = target_dir / f"{slug}-layout.json"
        payload = {
            "project_id": config.project_id,
            "saved_at": timestamp.isoformat(),
            "pattern_id": tracker_state.pattern_id,
            "pending_request_count": len(tracker_state.pending_requests),
            "import_asset_count": tracker_state.import_asset_count,
            "tutorial_tip_count": len(tracker_state.tutorial_tips),
        }
        if tracker_state.last_preview_summary is not None:
            payload["last_preview_summary"] = tracker_state.last_preview_summary
        checkpoint.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        attachments: List[Path] = []
        manifest_path = config.manifest_path or self._manifest_path
        if manifest_path is not None and Path(manifest_path).exists():
            manifest_copy = target_dir / f"{slug}-manifest.json"
            shutil.copy2(manifest_path, manifest_copy)
            attachments.append(manifest_copy)
        tracker_state.autosave_recovery_prompt = (
            f"Autosaved {config.project_id} at {slug}. Check .autosave/{config.project_id} for recovery."
        )
        return checkpoint, attachments


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
