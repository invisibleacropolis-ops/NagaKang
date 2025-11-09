"""Tracker pattern editing helpers for Step 4 sequencer foundations."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List

from domain.models import Pattern, PatternStep


@dataclass(frozen=True)
class StepMutation:
    """Record describing a single step mutation for auditing or undo."""

    mutation_id: str
    index: int
    previous: PatternStep
    updated: PatternStep


@dataclass(frozen=True)
class PlaybackRequest:
    """Lightweight playback job used by the upcoming sequencer queue."""

    mutation_id: str
    index: int
    start_beat: float
    duration_beats: float
    note: int | None
    velocity: int | None
    instrument_id: str | None


@dataclass
class MutationBatch:
    """Group of mutations that should undo/redo as a single unit."""

    batch_id: str
    label: str | None = None
    mutations: List[StepMutation] = field(default_factory=list)

    def __iter__(self) -> Iterator[StepMutation]:  # pragma: no cover - simple delegation
        return iter(self.mutations)

    def append(self, mutation: StepMutation) -> None:
        self.mutations.append(mutation)

    def __bool__(self) -> bool:  # pragma: no cover - trivial container hook
        return bool(self.mutations)


class PlaybackQueue:
    """In-memory FIFO queue that will drive preview renders in Step 4."""

    def __init__(self) -> None:
        self._pending: List[PlaybackRequest] = []

    def enqueue(
        self,
        mutation: StepMutation,
        *,
        start_beat: float,
        duration_beats: float,
    ) -> PlaybackRequest:
        request = PlaybackRequest(
            mutation_id=mutation.mutation_id,
            index=mutation.index,
            start_beat=start_beat,
            duration_beats=duration_beats,
            note=mutation.updated.note,
            velocity=mutation.updated.velocity,
            instrument_id=mutation.updated.instrument_id,
        )
        self._pending.append(request)
        return request

    def pop_next(self) -> PlaybackRequest | None:
        if not self._pending:
            return None
        return self._pending.pop(0)

    def clear(self) -> None:
        self._pending.clear()

    def __len__(self) -> int:  # pragma: no cover - simple delegation
        return len(self._pending)

    def __iter__(self):  # pragma: no cover - iteration sugar
        return iter(list(self._pending))


class PatternEditor:
    """In-memory helper that performs tracker-style mutations safely."""

    def __init__(self, pattern: Pattern, *, steps_per_beat: float = 4.0) -> None:
        self._pattern = pattern
        if steps_per_beat <= 0.0:
            raise ValueError("steps_per_beat must be positive")
        self._steps_per_beat = float(steps_per_beat)
        self._history: List[StepMutation] = []
        self._undo_stack: List[StepMutation | MutationBatch] = []
        self._redo_stack: List[StepMutation | MutationBatch] = []
        self._mutation_counter = 0
        self._batch_counter = 0
        self._active_batch: MutationBatch | None = None
        self._ensure_length(pattern.length_steps)

    @property
    def pattern(self) -> Pattern:
        """Return the underlying pattern reference."""

        return self._pattern

    @property
    def history(self) -> List[StepMutation]:
        """Return the recorded mutations in order of execution."""

        return list(self._history)

    @property
    def undo_stack(self) -> List[StepMutation | MutationBatch]:
        """Return the pending undo mutations (most recent last)."""

        return list(self._undo_stack)

    @property
    def redo_stack(self) -> List[StepMutation | MutationBatch]:
        """Return the pending redo mutations (most recent last)."""

        return list(self._redo_stack)

    @property
    def steps_per_beat(self) -> float:
        """Return the configured tracker resolution."""

        return self._steps_per_beat

    def step_to_beat(self, step_index: int) -> float:
        """Translate a pattern step index into its beat position."""

        if step_index < 0:
            raise IndexError("step_index must be non-negative")
        return step_index / self._steps_per_beat

    def steps_to_beats(self, steps: float) -> float:
        """Convert an arbitrary step span into beats respecting the resolution."""

        return max(0.0, float(steps)) / self._steps_per_beat

    def set_step(
        self,
        index: int,
        *,
        note: int | None = None,
        velocity: int | None = None,
        instrument_id: str | None = None,
    ) -> PatternStep:
        """Assign musical data to the requested step, extending the grid if needed."""

        step = self._get_step(index)
        previous = step.model_copy()
        payload = {}
        if note is not None:
            payload["note"] = note
        if velocity is not None:
            payload["velocity"] = velocity
        if instrument_id is not None:
            payload["instrument_id"] = instrument_id
        updated = step.model_copy(update=payload)
        self._commit(index, previous, updated)
        return updated

    def clear_step(self, index: int) -> PatternStep:
        """Reset the target step to a rest."""

        step = self._get_step(index)
        previous = step.model_copy()
        updated = PatternStep()
        self._commit(index, previous, updated)
        return updated

    def apply_effect(self, index: int, effect: str, value: float) -> PatternStep:
        """Apply or update a tracker step effect."""

        step = self._get_step(index)
        previous = step.model_copy()
        effects = dict(step.step_effects)
        effects[effect] = value
        updated = step.model_copy(update={"step_effects": effects})
        self._commit(index, previous, updated)
        return updated

    def duplicate_range(self, start: int, length: int, destination: int) -> List[int]:
        """Duplicate a slice of steps to a destination offset."""

        if length <= 0:
            return []
        self._ensure_length(self._pattern.length_steps)
        src_end = min(start + length, self._pattern.length_steps)
        dest_end = min(destination + (src_end - start), self._pattern.length_steps)
        copied: list[int] = []
        buffer = [self._get_step(idx).model_copy() for idx in range(start, src_end)]
        for offset, step in enumerate(buffer):
            target = destination + offset
            if target >= dest_end:
                break
            previous = self._get_step(target).model_copy()
            updated = step.model_copy()
            self._commit(target, previous, updated)
            copied.append(target)
        return copied

    def rotate_range(self, start: int, length: int, offset: int) -> List[int]:
        """Rotate a window of steps by the provided offset."""

        if length <= 0:
            return []
        window_end = min(start + length, self._pattern.length_steps)
        indices = list(range(start, window_end))
        if not indices:
            return []
        offset = offset % len(indices)
        if offset == 0:
            return []
        buffer = [self._get_step(idx).model_copy() for idx in indices]
        rotated = buffer[offset:] + buffer[:offset]
        touched: list[int] = []
        for idx, step in zip(indices, rotated):
            previous = self._get_step(idx).model_copy()
            updated = step.model_copy()
            self._commit(idx, previous, updated)
            touched.append(idx)
        return touched

    def step_summary(self, index: int) -> dict[str, object]:
        """Return a lightweight snapshot for UI previews."""

        step = self._get_step(index)
        return {
            "index": index,
            "note": step.note,
            "velocity": step.velocity,
            "instrument_id": step.instrument_id,
            "effects": dict(step.step_effects),
        }

    def mutation_preview_window(
        self,
        mutation: StepMutation,
        *,
        minimum_steps: float = 0.5,
    ) -> tuple[float, float]:
        """Return the beat window a playback preview should cover."""

        start = self.step_to_beat(mutation.index)
        effects = mutation.updated.step_effects
        duration = None
        if effects and "length_beats" in effects:
            try:
                duration = float(effects["length_beats"])
            except (TypeError, ValueError):
                duration = None
        if duration is None or duration <= 0.0:
            duration = self.steps_to_beats(1.0)
        minimum = self.steps_to_beats(minimum_steps)
        if duration < minimum:
            duration = minimum
        return start, duration

    def undo(self, steps: int = 1) -> List[StepMutation]:
        """Revert the most recent mutations, returning the applied records."""

        undone: List[StepMutation] = []
        for _ in range(min(max(steps, 0), len(self._undo_stack))):
            entry = self._undo_stack.pop()
            if isinstance(entry, MutationBatch):
                for mutation in reversed(entry.mutations):
                    self._pattern.steps[mutation.index] = mutation.previous.model_copy()
                    undone.append(mutation)
                self._redo_stack.append(entry)
            else:
                self._pattern.steps[entry.index] = entry.previous.model_copy()
                self._redo_stack.append(entry)
                undone.append(entry)
        return undone

    def redo(self, steps: int = 1) -> List[StepMutation]:
        """Reapply the most recently undone mutations in order."""

        replayed: List[StepMutation] = []
        for _ in range(min(max(steps, 0), len(self._redo_stack))):
            entry = self._redo_stack.pop()
            if isinstance(entry, MutationBatch):
                for mutation in entry.mutations:
                    self._pattern.steps[mutation.index] = mutation.updated.model_copy()
                    replayed.append(mutation)
                self._undo_stack.append(entry)
            else:
                self._pattern.steps[entry.index] = entry.updated.model_copy()
                self._undo_stack.append(entry)
                replayed.append(entry)
        return replayed

    def queue_mutation_preview(
        self,
        queue: PlaybackQueue,
        mutation: StepMutation,
        *,
        step_duration_beats: float | None = None,
        start_beat: float | None = None,
    ) -> PlaybackRequest:
        """Push a mutation onto the playback queue for forthcoming previews."""

        inferred_start: float | None = None
        inferred_duration: float | None = None
        if start_beat is None or step_duration_beats is None:
            inferred_start, inferred_duration = self.mutation_preview_window(mutation)
        start = start_beat if start_beat is not None else inferred_start if inferred_start is not None else self.step_to_beat(mutation.index)
        duration = (
            step_duration_beats
            if step_duration_beats is not None
            else inferred_duration if inferred_duration is not None else self.steps_to_beats(1.0)
        )
        return queue.enqueue(
            mutation,
            start_beat=start,
            duration_beats=duration,
        )

    @contextmanager
    def batch(self, label: str | None = None) -> Iterator[MutationBatch]:
        """Group multiple mutations so they undo/redo as a single frame."""

        if self._active_batch is not None:
            raise RuntimeError("Cannot nest PatternEditor batches")
        self._batch_counter += 1
        batch = MutationBatch(batch_id=f"batch_{self._batch_counter}", label=label)
        self._active_batch = batch
        try:
            yield batch
        finally:
            active = self._active_batch
            self._active_batch = None
            if active and active.mutations:
                self._undo_stack.append(active)
                self._redo_stack.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_length(self, target_length: int) -> None:
        if target_length <= 0:
            return
        while len(self._pattern.steps) < target_length:
            self._pattern.steps.append(PatternStep())

    def _next_mutation_id(self) -> str:
        self._mutation_counter += 1
        return f"mutation_{self._mutation_counter}"

    def _append_history(self, mutation: StepMutation) -> None:
        self._history.append(mutation)
        if self._active_batch is not None:
            if not self._active_batch.mutations:
                self._redo_stack.clear()
            self._active_batch.append(mutation)
        else:
            self._undo_stack.append(mutation)
            self._redo_stack.clear()

    def _get_step(self, index: int) -> PatternStep:
        if index < 0 or index >= self._pattern.length_steps:
            raise IndexError(f"Step index {index} out of range for pattern length {self._pattern.length_steps}")
        self._ensure_length(index + 1)
        return self._pattern.steps[index]

    def _commit(self, index: int, previous: PatternStep, updated: PatternStep) -> None:
        if previous == updated:
            return
        mutation = StepMutation(
            mutation_id=self._next_mutation_id(),
            index=index,
            previous=previous,
            updated=updated,
        )
        self._pattern.steps[index] = updated
        self._append_history(mutation)

    def iter_steps(self) -> Iterable[PatternStep]:
        """Yield steps up to the declared pattern length."""

        for idx in range(self._pattern.length_steps):
            yield self._get_step(idx)
