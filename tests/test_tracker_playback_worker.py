from domain.models import Pattern, PatternStep
from tracker import MutationPreviewService, PatternEditor
from tracker.playback_worker import PlaybackWorker


def _make_pattern(length: int = 8) -> Pattern:
    return Pattern(
        id="pattern",
        name="Pattern",
        length_steps=length,
        steps=[PatternStep() for _ in range(length)],
    )


def test_playback_worker_processes_requests_and_callbacks():
    pattern = _make_pattern(12)
    editor = PatternEditor(pattern, steps_per_beat=6.0)
    service = MutationPreviewService(editor)

    seen_indices: list[int] = []
    worker = PlaybackWorker(service, on_request=lambda request: seen_indices.append(request.index))

    with service.preview_batch("demo chord"):
        editor.set_step(0, note=60, velocity=100)
        editor.set_step(3, note=64, velocity=105)

    requests = worker.process_pending()
    assert [request.index for request in requests] == [0, 3]
    assert seen_indices == [0, 3]

    history = worker.processed_requests()
    assert len(history) == 2
    summary = worker.describe_request(history[0])
    assert summary["start_step"] == 0
    assert summary["end_step"] >= summary["start_step"]

