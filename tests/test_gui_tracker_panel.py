from domain.models import InstrumentDefinition, InstrumentModule, Pattern, PatternStep
import pytest

from gui.tracker_panel import (
    LoudnessTableWidget,
    TrackerGridWidget,
    TrackerPanelController,
    TransportControlsWidget,
)
from gui.state import TrackerPanelState
from tracker.pattern_editor import PatternEditor
from tracker.preview_service import MutationPreviewService


def build_pattern() -> Pattern:
    return Pattern(
        id="pattern_A",
        name="Pattern A",
        length_steps=16,
        steps=[PatternStep() for _ in range(16)],
    )


def test_tracker_panel_controller_queues_preview_for_selection() -> None:
    pattern = build_pattern()
    editor = PatternEditor(pattern)
    editor.set_step(0, note=64, velocity=100, instrument_id="lead")
    service = MutationPreviewService(editor)
    controller = TrackerPanelController(service, selection_window_steps=2.0)

    request = controller.preview_step(0)

    assert request.index == 0
    assert request.start_beat == 0.0
    assert request.duration_beats == editor.steps_to_beats(2.0)
    assert len(service.queue) == 1


def test_tracker_grid_widget_applies_state_and_selects_step() -> None:
    pattern = build_pattern()
    editor = PatternEditor(pattern)
    editor.set_step(1, note=60, velocity=80, instrument_id="lead")
    service = MutationPreviewService(editor)
    controller = TrackerPanelController(service)

    state = TrackerPanelState(
        pattern_id=pattern.id,
        pending_requests=[{"index": 1}],
        last_preview_summary={"max_lufs": -10.0},
        loudness_rows=[{"bucket": 0, "lufs": -12.0}],
    )

    widget = TrackerGridWidget()
    widget.bind_controller(controller)
    widget.apply_state(state)

    assert widget.pattern_id == pattern.id
    assert widget.pending_requests == state.pending_requests
    assert widget.last_preview_summary == state.last_preview_summary

    widget.select_step(1)

    assert widget.selected_step == 1
    assert len(service.queue) == 1


def test_loudness_table_widget_mirrors_state() -> None:
    state = TrackerPanelState(
        pattern_id="pattern_A",
        loudness_rows=[{"bucket": 0, "lufs": -14.0}]
    )

    widget = LoudnessTableWidget()
    widget.apply_state(state)

    assert widget.pattern_id == state.pattern_id
    assert widget.loudness_rows == state.loudness_rows


def test_transport_widget_binds_state_and_controls_preview() -> None:
    pattern = build_pattern()
    editor = PatternEditor(pattern)
    editor.set_step(0, note=60, velocity=90, instrument_id="lead")
    editor.set_step(4, note=65, velocity=100, instrument_id="lead")
    service = MutationPreviewService(editor)
    controller = TrackerPanelController(service)

    state = TrackerPanelState(
        pattern_id=pattern.id,
        tempo_bpm=132.0,
        is_playing=False,
        loop_window_steps=8.0,
        tutorial_tips=[
            "Tap the tracker grid to audition steps in place.",
            "Loop markers allow continuous playback for refinement.",
        ],
    )

    widget = TransportControlsWidget()
    widget.bind_controller(controller)
    widget.apply_state(state)

    assert widget.tempo_bpm == pytest.approx(132.0)
    assert widget.loop_window_steps == pytest.approx(8.0)
    assert widget.onboarding_hint.startswith("Tap the tracker grid")

    requests = widget.start_playback()

    assert widget.is_playing is True
    assert len(requests) == 2
    assert len(service.queue) == 2

    widget.stop_playback()

    assert widget.is_playing is False
    assert len(service.queue) == 0


def test_controller_preview_loop_respects_window() -> None:
    pattern = build_pattern()
    editor = PatternEditor(pattern)
    editor.set_step(0, note=60, velocity=90, instrument_id="lead")
    editor.set_step(8, note=72, velocity=100, instrument_id="pad")
    service = MutationPreviewService(editor)
    controller = TrackerPanelController(service)

    requests = controller.preview_loop(start_step=0, window_steps=4.0)

    assert len(requests) == 1
    assert requests[0].index == 0

    with pytest.raises(ValueError):
        controller.preview_loop(window_steps=0)
