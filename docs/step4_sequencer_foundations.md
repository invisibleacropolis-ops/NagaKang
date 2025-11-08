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

## Next steps

- Extend the editor with undo/redo stacks shared with the forthcoming Kivy UI.
- Introduce tempo-aware helpers that translate beats into step indices for the
  playback scheduler.
- Wire pattern mutations into a new sequencer service that synchronises
  `PatternEditor` with the offline render bridge created in Step 3.
