from domain.models import Pattern

from tracker import PatternEditor


def _make_pattern(length_steps: int = 8) -> Pattern:
    return Pattern(id="pat", name="Pattern", length_steps=length_steps)


def test_set_step_records_history():
    pattern = _make_pattern()
    editor = PatternEditor(pattern)

    updated = editor.set_step(0, note=60, velocity=100, instrument_id="vox")

    assert updated.note == 60
    assert updated.velocity == 100
    assert updated.instrument_id == "vox"
    assert len(editor.history) == 1
    mutation = editor.history[0]
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
