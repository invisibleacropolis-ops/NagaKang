"""Sequencer-facing helpers that queue pattern previews for Step 4."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, List

from .pattern_editor import (
    MutationBatch,
    PatternEditor,
    PlaybackQueue,
    PlaybackRequest,
    StepMutation,
)


class MutationPreviewService:
    """Coordinate pattern editor mutations with playback queue scheduling."""

    def __init__(self, editor: PatternEditor, queue: PlaybackQueue | None = None) -> None:
        self._editor = editor
        self._queue = queue or PlaybackQueue()

    @property
    def editor(self) -> PatternEditor:
        """Return the wrapped `PatternEditor` reference."""

        return self._editor

    @property
    def queue(self) -> PlaybackQueue:
        """Return the underlying playback queue."""

        return self._queue

    def enqueue_mutation(
        self,
        mutation: StepMutation,
        *,
        start_beat: float | None = None,
        step_duration_beats: float | None = None,
    ) -> PlaybackRequest:
        """Push a mutation preview into the queue using tempo-aware helpers."""

        return self._editor.queue_mutation_preview(
            self._queue,
            mutation,
            start_beat=start_beat,
            step_duration_beats=step_duration_beats,
        )

    @contextmanager
    def preview_batch(
        self,
        label: str | None = None,
        *,
        auto_preview: bool = True,
    ) -> Iterator[MutationBatch]:
        """Mirror `PatternEditor.batch` but queue previews for collected mutations."""

        with self._editor.batch(label) as batch:
            yield batch
        if auto_preview:
            for mutation in batch.mutations:
                self.enqueue_mutation(mutation)

    def drain_requests(self) -> List[PlaybackRequest]:
        """Return and clear all pending playback requests."""

        requests = list(self._queue)
        self._queue.clear()
        return requests

    def pending_requests(self) -> List[PlaybackRequest]:
        """Return a snapshot of pending requests without clearing the queue."""

        return list(self._queue)


__all__ = ["MutationPreviewService"]
