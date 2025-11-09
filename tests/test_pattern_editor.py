import pytest

from domain.models import Pattern, PatternStep
from tracker.pattern_editor import MutationBatch, PlaybackQueue, PatternEditor


def test_set_step_records_history():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)

    updated = editor.set_step(0, note=60, velocity=100, instrument_id="vox")

    assert updated.note == 60
    assert updated.velocity == 100
    assert updated.instrument_id == "vox"
    assert len(editor.history) == 1
    mutation = editor.history[0]
    assert mutation.mutation_id.startswith("mutation_")
    assert mutation.index == 0
    assert mutation.previous.note is None
    assert mutation.updated.note == 60


def test_apply_effect_and_clear_step():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)

    editor.apply_effect(1, "length_beats", 0.5)
    assert pattern.steps[1].step_effects["length_beats"] == 0.5

    editor.clear_step(1)
    assert pattern.steps[1].note is None
    assert pattern.steps[1].step_effects == {}
    assert len(editor.history) == 2


def test_duplicate_and_rotate_range():
    pattern = _make_pattern(16)
    editor = PatternEditor(pattern)
    editor.set_step(0, note=60, velocity=90)
    editor.set_step(1, note=62, velocity=95)

    copied = editor.duplicate_range(0, 2, 4)
    assert copied == [4, 5]
    assert pattern.steps[4].note == 60
    assert pattern.steps[5].velocity == 95

    rotated = editor.rotate_range(4, 4, 1)
    assert set(rotated) == {4, 5, 6, 7}
    assert pattern.steps[4].note == 62
    assert pattern.steps[5].note is None


def test_step_summary_matches_state():
    pattern = _make_pattern(4)
    editor = PatternEditor(pattern)
    editor.set_step(2, note=67, velocity=110, instrument_id="lead")
    editor.apply_effect(2, "slide", 1.0)

    summary = editor.step_summary(2)
    assert summary["note"] == 67
    assert summary["velocity"] == 110
    assert summary["instrument_id"] == "lead"
    assert summary["effects"] == {"slide": 1.0}


def test_mutation_ids_remain_unique_across_history():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)

    editor.set_step(0, note=60)
    editor.set_step(0, velocity=90)
    editor.apply_effect(0, "slide", 1.0)

    ids = [mutation.mutation_id for mutation in editor.history]
    assert ids == list(dict.fromkeys(ids))


def test_undo_and_redo_cycle_restores_steps():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)

    editor.set_step(0, note=60)
    editor.set_step(1, note=62)
    assert [step.note for step in pattern.steps[:2]] == [60, 62]
    assert len(editor.undo_stack) == 2
    assert not editor.redo_stack

    undone_first = editor.undo()
    assert [mutation.index for mutation in undone_first] == [1]
    assert pattern.steps[1].note is None
    assert len(editor.undo_stack) == 1
    assert len(editor.redo_stack) == 1

    editor.undo()
    assert pattern.steps[0].note is None
    assert not editor.undo_stack
    assert len(editor.redo_stack) == 2

    redo_first = editor.redo()
    assert [mutation.index for mutation in redo_first] == [0]
    assert pattern.steps[0].note == 60
    assert len(editor.undo_stack) == 1
    assert len(editor.redo_stack) == 1

    redo_second = editor.redo()
    assert [mutation.index for mutation in redo_second] == [1]
    assert pattern.steps[1].note == 62
    assert len(editor.undo_stack) == 2
    assert not editor.redo_stack


def test_queue_mutation_preview_enqueues_requests():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)
    editor.set_step(3, note=72, velocity=95, instrument_id="vox")
    mutation = editor.history[-1]

    queue = PlaybackQueue()
    request = editor.queue_mutation_preview(queue, mutation, step_duration_beats=0.5)

    assert request.mutation_id == mutation.mutation_id
    assert request.index == 3
    assert request.start_beat == pytest.approx(0.75)
    assert request.duration_beats == 0.5
    assert request.note == 72
    assert request.velocity == 95
    assert request.instrument_id == "vox"
    assert len(queue) == 1

    popped = queue.pop_next()
    assert popped == request
    assert queue.pop_next() is None


def test_batch_groups_mutations_for_undo_redo():
    pattern = _make_pattern(8)
    editor = PatternEditor(pattern)

    with editor.batch("drag chord"):
        editor.set_step(0, note=60)
        editor.set_step(1, note=64)
        editor.set_step(2, note=67)

    assert len(editor.history) == 3
    assert len(editor.undo_stack) == 1
    batch_entry = editor.undo_stack[-1]
    assert isinstance(batch_entry, MutationBatch)
    assert [mutation.index for mutation in batch_entry.mutations] == [0, 1, 2]

    undone = editor.undo()
    assert [mutation.index for mutation in undone] == [2, 1, 0]
    assert all(pattern.steps[idx].note is None for idx in range(3))
    assert len(editor.redo_stack) == 1

    replayed = editor.redo()
    assert [mutation.index for mutation in replayed] == [0, 1, 2]
    assert pattern.steps[0].note == 60
    assert pattern.steps[1].note == 64
    assert pattern.steps[2].note == 67


def test_step_to_beat_and_preview_window_respect_resolution():
    pattern = _make_pattern(16)
    editor = PatternEditor(pattern, steps_per_beat=8.0)
    editor.set_step(4, note=70, velocity=105, instrument_id="vox")
    editor.apply_effect(4, "length_beats", 1.25)
    mutation = editor.history[-1]

    assert editor.step_to_beat(4) == pytest.approx(0.5)
    start, duration = editor.mutation_preview_window(mutation)
    assert start == pytest.approx(0.5)
    assert duration == pytest.approx(1.25)

    queue = PlaybackQueue()
    request = editor.queue_mutation_preview(queue, mutation)
    assert request.start_beat == pytest.approx(0.5)
    assert request.duration_beats == pytest.approx(1.25)


def _make_pattern(length: int = 8) -> Pattern:
    return Pattern(
        id="pattern",
        name="Pattern",
        length_steps=length,
        steps=[PatternStep() for _ in range(length)],
    )
