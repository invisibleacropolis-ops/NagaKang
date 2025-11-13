# Step 7 GUI/UX Shell Kickoff

This note records the first deliverables for Plan §7 (GUI/UX Implementation with Kivy) and links the code scaffolding that now lives in `src/gui/`. The goal is to provide a documented, testable shell before higher-fidelity widgets land.

## Objectives Recap
- Confirmed Step 6 prerequisites and mixer telemetry coverage via README §6–§7 review before wiring the GUI shell.
- Stood up a preview orchestration layer that consumes the existing tracker playback worker plus Step 6 mixer adapters.
- Defined widget contracts so external Kivy contributors can bind real layouts without spelunking through audio code.

## Application Shell
- `src/gui/app.py` introduces `TrackerMixerApp` and `TrackerMixerRoot`. The root widget polls a `PreviewOrchestrator`, stores the latest `TrackerMixerLayoutState`, and exposes the object via `layout_state` for downstream Kivy bindings.
- The shell guards all Kivy imports with documented fallbacks so CI and headless developer environments can import the package without installing GPU-heavy dependencies.

## Tracker Panel Widgets & Controller
- `src/gui/tracker_panel.py` adds `TrackerGridWidget`, `LoudnessTableWidget`, and `TransportControlsWidget`. All widgets accept a `TrackerPanelState` via `apply_state(...)` so KV contributors can hydrate pattern metadata, pending preview queue entries, loudness analytics, and transport/tutorial state without touching backend types.
- `TrackerGridWidget.select_step(...)` mirrors tracker gestures back into the preview pipeline via `TrackerPanelController`, updating the `selected_step` property so multi-touch bindings can surface focus/selection affordances.
- `TrackerPanelController` wraps `MutationPreviewService` and builds ephemeral `StepMutation` records for selection previews. The controller takes a configurable `selection_window_steps` window to match tracker resolution, calls `PatternEditor.step_to_beat(...)` helpers for timing, and enqueues the resulting playback request automatically. Its new `preview_loop(...)` helper batches loop playback windows for the transport controls so KV layouts can trigger Step 1-style audition loops without rewriting queue logic.
- `LoudnessTableWidget` mirrors `TrackerPanelState.loudness_rows`, enabling doc/test instrumentation of the beat-wise LUFS grades required by Plan §7 and the README loudness milestone.
- `TransportControlsWidget` surfaces play/stop toggles, tempo readouts, loop-length controls, and the Step 1 onboarding copy captured in `TrackerPanelState.tutorial_tips`. Binding the widget to `TrackerPanelController.preview_loop(...)` keeps transport gestures synchronized with the backend preview queue, while `stop_playback()` clears queued auditions for deterministic Kivy demos.

## Preview Orchestration
- `src/gui/preview.py` wraps `tracker.playback_worker.PlaybackWorker` with a `PreviewOrchestrator` that:
  - Drains pending pattern preview requests and mirrors the tracker queue state for UI summaries.
  - Optionally delegates loudness table generation to `PatternPerformanceBridge.tracker_loudness_rows` (or any callable) per Plan §7 meter/visualisation requirements.
  - Hydrates mixer strip state via the shared `MixerBoardAdapter`, ensuring the tracker screen and mixer panel are synchronized with the same render batch.
- `PreviewBatchState` captures both the `TrackerMixerLayoutState` (for widgets) and raw `PreviewRender` objects (for logging/QA overlays) so future UI instrumentation has full fidelity.

## Widget & State Contracts
- `src/gui/state.py` defines dataclasses (`TrackerPanelState`, `MixerPanelState`, `TrackerMixerLayoutState`) that describe what each panel expects. External contributors can treat these as stable contracts when creating KV templates. `TrackerPanelState` now exposes tempo, `is_playing`, `loop_window_steps`, and `tutorial_tips` so transport widgets can echo the Step 1 UX copy and telemetry.
- `src/gui/mixer_board.py` promotes the MixerGraph → strip adapter from the Step 6 mock into production code, including:
  - `MixerStripState` plain-data records for strip hydration.
  - `MixerStripWidget` placeholder that documents the properties/gestures widgets must implement.
  - `MixerBoardAdapter` helpers for binding channel/return strips, reordering inserts, and pulling master meters for dashboard widgets.

## Next UI Tasks
1. Flesh out tracker-side widgets (grid, loudness table, transport) that consume `TrackerPanelState`.
2. Bind return/insert gestures in KV language, referencing the adapter helpers documented above.
3. Thread tutorial/tooltips copy from Step 1 UX docs into the new shell once widgets render live audio previews.

## Update History
- 2025-11-21 – Initial scaffolding capturing the preview orchestrator, layout state contracts, and mixer adapter promotion for Step 7 kickoff.
- 2025-11-22 – Added transport controls, tutorial tooltips sourced from Step 1 UX flows, and loop preview helpers binding the tracker shell to `TrackerPanelController`.
