import pytest

from audio.engine import EngineConfig, TempoMap
from audio.tracker_bridge import PatternPerformanceBridge
from domain.models import InstrumentDefinition, InstrumentModule, Pattern, PatternStep
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


def test_playback_worker_streams_requests_into_pattern_bridge():
    pytest.importorskip("numpy")

    pattern = _make_pattern(8)
    editor = PatternEditor(pattern, steps_per_beat=4.0)
    service = MutationPreviewService(editor)

    config = EngineConfig(sample_rate=12_000, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)
    instrument = InstrumentDefinition(
        id="tone",
        name="Preview Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine_oscillator",
                parameters={"amplitude": 0.35, "frequency_hz": 330.0},
            ),
            InstrumentModule(
                id="env",
                type="amplitude_envelope",
                parameters={"attack_ms": 8.0, "release_ms": 120.0},
                inputs=["osc"],
            ),
        ],
    )
    bridge = PatternPerformanceBridge(config, tempo)

    render_summaries: list[dict[str, object]] = []
    worker = PlaybackWorker(
        service,
        bridge=bridge,
        instruments={instrument.id: instrument},
        default_instrument_id=instrument.id,
        on_render=lambda preview: render_summaries.append(preview.to_summary()),
    )

    with service.preview_batch("paint two steps"):
        editor.set_step(0, note=60, velocity=100, instrument_id=instrument.id)
        editor.set_step(2, note=64, velocity=110, instrument_id=instrument.id)

    worker.process_pending()

    renders = worker.last_render_batch()
    assert len(renders) == 2
    assert len(worker.preview_history()) == 2
    assert len(render_summaries) == 2
    assert all(summary["window_frames"] > 0 for summary in render_summaries)
    assert all(summary["peak_amplitude"] >= summary["rms_amplitude"] for summary in render_summaries)


@pytest.mark.asyncio
async def test_playback_worker_process_pending_async_matches_sync():
    pattern = _make_pattern(4)
    editor = PatternEditor(pattern, steps_per_beat=4.0)
    service = MutationPreviewService(editor)
    worker = PlaybackWorker(service)

    editor.set_step(1, note=67, velocity=105)
    service.enqueue_mutation(editor.history[-1])

    requests = await worker.process_pending_async()
    assert len(requests) == 1
    assert worker.processed_requests()[-1].index == 1

