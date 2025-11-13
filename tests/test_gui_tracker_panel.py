from domain.models import InstrumentDefinition, InstrumentModule, Pattern, PatternStep
from gui.tracker_panel import (
    LoudnessTableWidget,
    TrackerGridWidget,
    TrackerPanelController,
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
