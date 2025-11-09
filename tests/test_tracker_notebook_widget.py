import importlib

import pytest

from tracker.pattern_editor import PlaybackRequest
from tracker.playback_worker import PreviewRender


@pytest.fixture()
def widget_module():
    module = importlib.import_module("docs.step3_tracker_notebook_widget")
    return module


@pytest.mark.requires_numpy
def test_preview_render_cache_downsamples_waveforms(widget_module, monkeypatch):
    np = pytest.importorskip("numpy")

    request = PlaybackRequest(
        mutation_id="mut-1",
        index=0,
        start_beat=1.0,
        duration_beats=0.5,
        note=60,
        velocity=110,
        instrument_id="lead",
    )
    buffer = np.linspace(-1.0, 1.0, num=48, dtype=float)
    stereo = np.stack([buffer, buffer * 0.5], axis=1)
    playback = type("Playback", (), {"buffer": stereo})()

    preview = PreviewRender(
        request=request,
        playback=playback,
        window_buffer=stereo,
        start_frame=0,
        end_frame=48,
        sample_rate=48_000,
    )

    cache = widget_module.PreviewRenderCache(max_entries=2, waveform_points=6)
    summary = cache.add_preview(preview)
    assert summary["label"] == "mut-1"
    assert len(summary["waveform_preview"]) == 6
    assert cache.rows()[0]["peak_amplitude"] >= cache.rows()[0]["rms_amplitude"]

    # Ensure cache trims when exceeding capacity
    request_2 = request.__class__(
        mutation_id="mut-2",
        index=1,
        start_beat=2.0,
        duration_beats=0.5,
        note=62,
        velocity=105,
        instrument_id="lead",
    )
    preview_2 = PreviewRender(
        request=request_2,
        playback=playback,
        window_buffer=stereo,
        start_frame=48,
        end_frame=96,
        sample_rate=48_000,
    )
    cache.add_preview(preview_2)

    request_3 = request.__class__(
        mutation_id="mut-3",
        index=2,
        start_beat=3.0,
        duration_beats=0.5,
        note=64,
        velocity=100,
        instrument_id="lead",
    )
    preview_3 = PreviewRender(
        request=request_3,
        playback=playback,
        window_buffer=stereo,
        start_frame=96,
        end_frame=144,
        sample_rate=48_000,
    )
    cache.add_preview(preview_3)

    labels = [row["label"] for row in cache.rows()]
    assert labels == ["mut-2", "mut-3"]


@pytest.mark.requires_numpy
def test_preview_render_widget_fallback(widget_module, monkeypatch):
    np = pytest.importorskip("numpy")
    cache = widget_module.PreviewRenderCache(max_entries=1, waveform_points=4)

    request = PlaybackRequest(
        mutation_id="mut-1",
        index=0,
        start_beat=0.0,
        duration_beats=1.0,
        note=60,
        velocity=100,
        instrument_id="bass",
    )
    stereo = np.ones((10, 2))
    playback = type("Playback", (), {"buffer": stereo})()
    preview = PreviewRender(
        request=request,
        playback=playback,
        window_buffer=stereo,
        start_frame=0,
        end_frame=10,
        sample_rate=48_000,
    )
    cache.add_preview(preview)

    monkeypatch.setattr(widget_module, "widgets", None)
    text = widget_module.build_preview_render_widget(cache.rows())
    assert "Preview Render Overview" in text
    assert "mut-1" in text
