# Step 7 GUI/UX Shell Kickoff

This note records the first deliverables for Plan §7 (GUI/UX Implementation with Kivy) and links the code scaffolding that now lives in `src/gui/`. The goal is to provide a documented, testable shell before higher-fidelity widgets land.

## Objectives Recap
- Confirmed Step 6 prerequisites and mixer telemetry coverage via README §6–§7 review before wiring the GUI shell.
- Stood up a preview orchestration layer that consumes the existing tracker playback worker plus Step 6 mixer adapters.
- Defined widget contracts so external Kivy contributors can bind real layouts without spelunking through audio code.

## Application Shell
- `src/gui/app.py` introduces `TrackerMixerApp` and `TrackerMixerRoot`. The root widget polls a `PreviewOrchestrator`, stores the latest `TrackerMixerLayoutState`, and exposes the object via `layout_state` for downstream Kivy bindings.
- `TrackerMixerRoot` now instantiates `TransportControlsWidget`, `TrackerGridWidget`, and `LoudnessTableWidget` inside a dedicated tracker column before mounting the new `MixerDockWidget` beside it. This mirrors the Step 7 three-panel mock so layout stress tests hit the intended spacing even without KV templates. Passing a `TrackerPanelController` into `TrackerMixerApp` automatically binds the transport and grid gestures to the preview queue, which keeps Step 7 transport actions aligned with the Step 4 playback worker.
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
- The orchestrator now exposes `tempo_bpm`, transport playback status, loop-window defaults, and tutorial copy alongside tracker summaries. Callers can override these via the constructor parameters (`tempo_bpm`, `loop_window_steps`, `tutorial_tips`) to keep Step 1 onboarding copy and rehearsal tempos consistent across demos.

### Loop-Length KV Binding Example

The loop-length control is intentionally stored on `TransportControlsWidget.loop_window_steps` so KV authors can bind sliders or steppers directly. A minimal binding looks like:

```kv
#:kivy 2.3.0
<TransportControlsRow@BoxLayout>:
    orientation: "horizontal"
    TransportControlsWidget:
        id: transport
        on_stop: transport.stop_playback()
    Slider:
        min: 1
        max: 32
        value: transport.loop_window_steps
        step: 1
        on_value: transport.loop_window_steps = int(self.value)
```

This keeps loop audition gestures in sync with the tracker queue without duplicating controller logic. Real layouts can wrap the slider with labeled buttons/tooltips referencing `transport.onboarding_hint` for the Step 1 tutorial text.

### Transport Strip Tutorial Polish

To keep Step 1 onboarding copy front-and-center we added `TransportControlsWidget.tutorial_tip_index` plus `advance_tutorial_hint()` for callouts and annotated demos. The widget now clamps slider/stepper input via `set_loop_window_steps(...)` so KV bindings cannot accidentally pass invalid values into the preview worker. The annotated mock below shows how the new helpers line up with the Plan §7 transport deliverables:

![Annotated transport controls strip with onboarding hint callouts](assets/ui/transport_strip_annotations.svg)

The following snippet demonstrates the recommended bindings for TrackerMixerApp demos. The `Play`, `Stop`, and `Next Tip` buttons simply proxy into the widget helpers, keeping the logic testable and aligned with the regression suite:

```kv
#:kivy 2.3.0
<TransportStrip@BoxLayout>:
    spacing: 12
    TransportControlsWidget:
        id: transport
    BoxLayout:
        size_hint_x: 0.6
        spacing: 8
        Button:
            text: "Play"
            on_press: transport.start_playback()
        Button:
            text: "Stop"
            on_press: transport.stop_playback()
        Button:
            text: "Next Tip"
            on_press: transport.advance_tutorial_hint()
        Slider:
            min: 1
            max: 32
            value: transport.loop_window_steps
            on_value: transport.set_loop_window_steps(self.value)
```

Binding these helpers directly ensures the TrackerMixerApp shell stays declarative while honoring the Step 1 onboarding narrative and transport polish targets captured in the README and EngineerLog.

## Widget & State Contracts
- `src/gui/state.py` defines dataclasses (`TrackerPanelState`, `MixerPanelState`, `TrackerMixerLayoutState`) that describe what each panel expects. External contributors can treat these as stable contracts when creating KV templates. `TrackerPanelState` now exposes tempo, `is_playing`, `loop_window_steps`, and `tutorial_tips` so transport widgets can echo the Step 1 UX copy and telemetry.
- `src/gui/mixer_board.py` promotes the MixerGraph → strip adapter from the Step 6 mock into production code, including:
  - `MixerStripState` plain-data records for strip hydration.
  - `MixerStripWidget` placeholder that documents the properties/gestures widgets must implement.
  - `MixerBoardAdapter` helpers for binding channel/return strips, reordering inserts, and pulling master meters for dashboard widgets.
  - `MixerDockWidget`, which clones `MixerStripWidget` instances for channel/return strips, updates master-bus meters, and exposes the containers that KV authors can style without reimplementing adapter logic.

## Layout Stress & Mixer Dock Wiring

- The tracker column now defaults to ~60% width while the mixer dock consumes the remaining ~40%, matching the annotated tablet mock from Plan §7. Engineers can tweak the split via KV templates while retaining the documented widget hierarchy.
- `MixerDockWidget` dynamically adds/removes strip widgets based on `MixerPanelState`, ensuring CI demos and layout rehearsals show the same strip count as the mixer graph. The regression suite covers the lifecycle via `tests/test_gui_mixer_board.py`.
- Polling the orchestrator at 500 ms keeps tracker telemetry and mixer meters within ~12 ms of each other under synthetic stress. These notes should accompany screenshots when sharing the layout shell with outside Kivy contributors.

## Next UI Tasks
1. Flesh out tracker-side widgets (grid, loudness table, transport) that consume `TrackerPanelState`.
2. Bind return/insert gestures in KV language, referencing the adapter helpers documented above.
3. Thread tutorial/tooltips copy from Step 1 UX docs into the new shell once widgets render live audio previews.

## Update History
- 2025-11-21 – Initial scaffolding capturing the preview orchestrator, layout state contracts, and mixer adapter promotion for Step 7 kickoff.
- 2025-11-22 – Added transport controls, tutorial tooltips sourced from Step 1 UX flows, and loop preview helpers binding the tracker shell to `TrackerPanelController`.
- 2025-11-23 – Threaded transport widgets directly into `TrackerMixerApp`, added tempo/tutorial parameters to `PreviewOrchestrator`, and documented the KV loop-length binding strategy.
- 2025-11-24 – Wired the tracker column into the mixer dock, documented layout stress constraints, and captured mixer trend pointers for CI handoff.
