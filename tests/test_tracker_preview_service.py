from domain.models import Pattern, PatternStep
from tracker import MutationPreviewService, PatternEditor


def _make_pattern(length: int = 8) -> Pattern:
    return Pattern(
        id="pattern",
        name="Pattern",
        length_steps=length,
        steps=[PatternStep() for _ in range(length)],
    )


def test_preview_batch_enqueues_requests_with_tempo_awareness():
    pattern = _make_pattern(12)
    editor = PatternEditor(pattern, steps_per_beat=6.0)
    service = MutationPreviewService(editor)

    with service.preview_batch("paint chord"):
        editor.set_step(0, note=60, velocity=100)
        editor.set_step(3, note=64, velocity=110)
        editor.apply_effect(3, "length_beats", 1.5)

    requests = service.drain_requests()
    assert [request.index for request in requests] == [0, 3, 3]
    assert requests[0].start_beat == 0.0
    assert requests[0].duration_beats == editor.steps_to_beats(1.0)
    assert requests[1].start_beat == editor.step_to_beat(3)
    assert requests[1].duration_beats == editor.steps_to_beats(1.0)
    assert requests[2].start_beat == editor.step_to_beat(3)
    assert requests[2].duration_beats == 1.5


def test_preview_batch_can_skip_auto_preview():
    pattern = _make_pattern(4)
    editor = PatternEditor(pattern)
    service = MutationPreviewService(editor)

    with service.preview_batch("silent edit", auto_preview=False):
        editor.set_step(1, note=72)

    assert service.pending_requests() == []

    mutation = editor.history[-1]
    service.enqueue_mutation(mutation, start_beat=2.5, step_duration_beats=0.25)

    requests = service.drain_requests()
    assert len(requests) == 1
    assert requests[0].start_beat == 2.5
    assert requests[0].duration_beats == 0.25
