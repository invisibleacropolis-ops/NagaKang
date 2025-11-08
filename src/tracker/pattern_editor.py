"""Tracker pattern editing helpers for Step 4 sequencer foundations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from domain.models import Pattern, PatternStep


@dataclass(frozen=True)
class StepMutation:
    """Record describing a single step mutation for auditing or undo."""

    index: int
    previous: PatternStep
    updated: PatternStep


class PatternEditor:
    """In-memory helper that performs tracker-style mutations safely."""

    def __init__(self, pattern: Pattern) -> None:
        self._pattern = pattern
        self._history: List[StepMutation] = []
        self._ensure_length(pattern.length_steps)

    @property
    def pattern(self) -> Pattern:
        """Return the underlying pattern reference."""

        return self._pattern

    @property
    def history(self) -> List[StepMutation]:
        """Return the recorded mutations in order of execution."""

        return list(self._history)

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_length(self, target_length: int) -> None:
        if target_length <= 0:
            return
        while len(self._pattern.steps) < target_length:
            self._pattern.steps.append(PatternStep())

    def _get_step(self, index: int) -> PatternStep:
        if index < 0 or index >= self._pattern.length_steps:
            raise IndexError(f"Step index {index} out of range for pattern length {self._pattern.length_steps}")
        self._ensure_length(index + 1)
        return self._pattern.steps[index]

    def _commit(self, index: int, previous: PatternStep, updated: PatternStep) -> None:
        if previous == updated:
            return
        self._pattern.steps[index] = updated
        self._history.append(StepMutation(index=index, previous=previous, updated=updated))

    def iter_steps(self) -> Iterable[PatternStep]:
        """Yield steps up to the declared pattern length."""

        for idx in range(self._pattern.length_steps):
            yield self._get_step(idx)
