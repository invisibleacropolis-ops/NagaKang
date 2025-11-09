# Step 4 Sequencer Foundations – Pattern Editing Kickoff

Step 4 focuses on the tracker engine and pattern editing logic. This session
introduces `tracker.PatternEditor`, giving external engineers a concrete API for
mutating `domain.models.Pattern` instances while keeping mutation history for
future undo/redo support.

## PatternEditor capabilities

- `set_step(index, note, velocity, instrument_id)` – writes tracker data into a
  step and records the mutation for audits.
- `apply_effect(index, command, value)` – updates tracker-style step effects
  without mutating the original dict in-place.
- `duplicate_range(start, length, destination)` – copies a slice of steps to a
  new location, respecting the declared pattern length.
- `rotate_range(start, length, offset)` – rotates a window of steps, useful for
  quick groove experimentation before the playback engine lands.
- `step_summary(index)` – surfaces lightweight info for UI previews (note,
  velocity, instrument, effects).
- `step_to_beat(index)` / `steps_to_beats(count)` – translate tracker grid
  indices into beat values using the configurable `steps_per_beat` resolution so
  sequencer services can stay tempo-aware without duplicating math.
- `beats_to_steps(beats)` / `beat_to_step(beat_position)` /
  `beat_window_to_step_range(start_beat, duration)` – expose the inverse helper
  set so the playback worker can translate preview beats back into step windows
  when scheduling renders or annotating CLI output.
- `undo(steps)` / `redo(steps)` – revert or replay the most recent mutations
  while exposing `undo_stack` / `redo_stack` so the UI can reflect pending
  history. Each mutation carries a stable `mutation_id` that ties into the
  automation smoothing identifiers logged by Step 3.
- `batch(label)` – context manager that groups multiple edits into a single
  undo/redo frame, ensuring drag gestures or chord entries roll back together.
- `mutation_preview_window(mutation)` – returns the tempo-aware beat window a
  preview should cover, factoring in per-step `length_beats` effects.
- `queue_mutation_preview(queue, mutation, step_duration_beats)` – pushes a
  playback request into the new `PlaybackQueue` stub so the sequencer can render
  previews without blocking the main tracker grid. When duration overrides are
  omitted the helper now derives beat timing from `mutation_preview_window()` so
  playback stays aligned to the configured resolution.

## PlaybackQueue stub

- `PlaybackQueue.enqueue(mutation, start_beat, duration_beats)` returns a
  `PlaybackRequest` containing the mutation ID, beat window, and musical data.
- The stub stores requests in FIFO order, exposing `pop_next()`/`clear()` to let
  the forthcoming sequencer service stream them into `PatternPerformanceBridge`
  renders.
- This structure mirrors the architecture sketches in the Comprehensive Plan
  (README §4), keeping playback orchestration separate from pattern editing so
  undo/redo remains instant even while offline renders spin.

## MutationPreviewService prototype

- `tracker.preview_service.MutationPreviewService` wraps a `PatternEditor` and
  `PlaybackQueue`, providing high-level helpers that coordinate undo batches with
  preview scheduling.
- `preview_batch(label)` mirrors `PatternEditor.batch` but automatically queues
  previews for each mutation once the block exits, ensuring drag gestures render
  together without blocking the UI thread.
- `enqueue_mutation(mutation, start_beat=None, step_duration_beats=None)` defers
  to the editor's tempo-aware helpers so preview durations stay correct across
  different `steps_per_beat` values.
- `drain_requests()` hands the queued `PlaybackRequest` objects back to the
  sequencer service so Step 4 prototypes can hand them to
  `PatternPerformanceBridge` for offline renders.

## PlaybackWorker prototype

- `tracker.playback_worker.PlaybackWorker` owns a
  `MutationPreviewService`, draining preview requests in FIFO order and
  broadcasting each to registered callbacks.
- `describe_request(request)` folds in the editor's beat/step helpers so CLI
  demos can log both beat and tracker step windows without repeating math.
- When a `PatternPerformanceBridge` is supplied the worker now renders
  `PreviewRender` windows for each `PlaybackRequest`, including peak and RMS
  amplitudes and step-aligned frame slices for tracker overlays.
- `process_pending_async()` mirrors the synchronous drain but executes in a
  background thread so UI event loops can keep painting while previews stream.
- The tracker CLI skeleton (`prototypes/audio_engine_skeleton.py`) records both
  the request summaries and render metrics (frames, seconds, peak/rms) when
  `--tracker-preview-demo` is enabled.

### Preview callback wiring

```
MutationPreviewService → PlaybackWorker.process_pending()
    ├─ request callbacks (CLI summaries / undo breadcrumbs)
    └─ PatternPerformanceBridge.render_pattern()
         └─ render callbacks (PreviewRender.to_summary → audio metrics)
```

The callback flow keeps tracker UI code simple: gesture handlers only need to
enqueue mutations, while preview dashboards subscribe to either the request or
render stream depending on whether they present beats, steps, or amplitude data.

## Tracker-grid gesture sketch

- **Tap / keyboard entry:** Call `PatternEditor.set_step()` then pass the final
  mutation to `MutationPreviewService.enqueue_mutation()` so single notes preview
  instantly.
- **Drag chord paint:** Wrap the gesture in `MutationPreviewService.preview_batch(
  "paint chord")` so undo/redo is atomic and the resulting playback queue emits
  one request per touched step.
- **Velocity ramp brush:** Combine `PatternEditor.apply_effect()` calls inside a
  preview batch; downstream automation overlays receive the matching mutation
  IDs for smoothing dashboards.
- **Range rotate / duplicate:** Use the editor helpers, then iterate the batch's
  mutations to queue previews selectively (e.g., only the destination slice)
  before draining the queue into the playback worker thread.

## Next steps

- Wire `PlaybackQueue` into a sequencer service that streams preview requests to
  `PatternPerformanceBridge` without blocking the tracker grid.
- Sketch tracker-grid interaction flows that map pointer/multi-touch gestures to
  `PatternEditor` calls, annotate which gestures enqueue playback previews vs.
  silent edits, and capture those flows in the Step 4 design notebook.
