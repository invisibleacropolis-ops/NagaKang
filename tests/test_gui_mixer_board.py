from audio.mixer import MeterReading

from gui.mixer_board import (
    MixerDockController,
    MixerDockWidget,
    MixerInsertGestureModel,
    MixerStripState,
)
from gui.state import MixerPanelState


class DummyStrip:
    def __init__(self) -> None:
        self.state = None

    def apply_state(self, state: MixerStripState) -> None:
        self.state = state


def build_panel_state() -> MixerPanelState:
    lead_strip = MixerStripState(
        name="Lead",
        fader_db=-3.0,
        pan=0.0,
        post_fader_meter=MeterReading(-6.0, -9.0),
        subgroup_meter=MeterReading(-9.0, -12.0),
        sends={"drum_room": -12.0},
        insert_order=["EQ"],
    )
    return_strip = MixerStripState(
        name="Plate",
        fader_db=-6.0,
        pan=0.0,
        post_fader_meter=MeterReading(-float("inf"), -float("inf")),
        subgroup_meter=None,
        sends={},
        insert_order=["Reverb"],
        is_return=True,
        return_level_db=-6.0,
    )
    return MixerPanelState(
        strip_states={"Lead": lead_strip},
        return_states={"Plate": return_strip},
        master_meter=MeterReading(-3.0, -6.0),
    )


def test_mixer_dock_widget_applies_panel_state() -> None:
    dock = MixerDockWidget(strip_factory=DummyStrip)
    state = build_panel_state()

    dock.apply_state(state)

    assert dock.master_peak_db == state.master_meter.peak_db
    assert dock.master_rms_db == state.master_meter.rms_db
    assert "Lead" in dock._channel_widgets
    assert dock._channel_widgets["Lead"].state is state.strip_states["Lead"]
    assert "Plate" in dock._return_widgets
    assert dock._return_widgets["Plate"].state is state.return_states["Plate"]
    assert dock.strip_container.children
    assert dock.return_container.children


def test_mixer_dock_widget_handles_removed_strips() -> None:
    dock = MixerDockWidget(strip_factory=DummyStrip)
    state = build_panel_state()
    dock.apply_state(state)

    next_state = MixerPanelState(
        strip_states={},
        return_states={},
        master_meter=None,
    )
    dock.apply_state(next_state)

    assert not dock.strip_container.children
    assert not dock.return_container.children
    assert dock.master_peak_db == -float("inf")
    assert dock.master_rms_db == -float("inf")


class AdapterStub:
    def __init__(self) -> None:
        self.state = MixerStripState(
            name="Lead",
            fader_db=-3.0,
            pan=0.0,
            post_fader_meter=MeterReading(-6.0, -9.0),
            subgroup_meter=None,
            sends={},
            insert_order=["EQ", "Compressor", "Limiter"],
        )
        self.reorder_calls: list[tuple[str, int, int]] = []

    def reorder_channel_inserts(self, channel_name: str, from_index: int, to_index: int) -> None:
        self.reorder_calls.append((channel_name, from_index, to_index))
        order = list(self.state.insert_order)
        moved = order.pop(from_index)
        order.insert(to_index, moved)
        self.state = MixerStripState(
            name=self.state.name,
            fader_db=self.state.fader_db,
            pan=self.state.pan,
            post_fader_meter=self.state.post_fader_meter,
            subgroup_meter=self.state.subgroup_meter,
            sends=self.state.sends,
            insert_order=order,
        )

    def strip_state(self, channel_name: str) -> MixerStripState:
        return self.state


def test_mixer_dock_widget_routes_insert_reorder_gestures() -> None:
    adapter = AdapterStub()
    controller = MixerDockController(adapter)  # type: ignore[arg-type]
    dock = MixerDockWidget()
    dock.bind_controller(controller)
    state = MixerPanelState(strip_states={"Lead": adapter.state}, master_meter=None)
    dock.apply_state(state)

    widget = dock._channel_widgets["Lead"]
    updated_order = widget.request_insert_reorder(0, 2)

    assert adapter.reorder_calls == [("Lead", 0, 2)]
    assert updated_order == ["Compressor", "Limiter", "EQ"]


def test_mixer_insert_gesture_model_previews_and_commits() -> None:
    adapter = AdapterStub()
    controller = MixerDockController(adapter)  # type: ignore[arg-type]
    dock = MixerDockWidget()
    dock.bind_controller(controller)
    state = MixerPanelState(strip_states={"Lead": adapter.state}, master_meter=None)
    dock.apply_state(state)
    model = MixerInsertGestureModel(dock)

    start_order = model.begin_drag("Lead", 1)
    assert start_order == ["EQ", "Compressor", "Limiter"]

    preview = model.preview_to(0)
    assert preview == ["Compressor", "EQ", "Limiter"]
    assert dock._channel_widgets["Lead"].insert_order == preview

    committed = model.commit()
    assert committed == preview
    assert adapter.reorder_calls[-1] == ("Lead", 1, 0)


def test_mixer_insert_gesture_model_cancel_restores_original_order() -> None:
    adapter = AdapterStub()
    controller = MixerDockController(adapter)  # type: ignore[arg-type]
    dock = MixerDockWidget()
    dock.bind_controller(controller)
    state = MixerPanelState(strip_states={"Lead": adapter.state}, master_meter=None)
    dock.apply_state(state)
    model = MixerInsertGestureModel(dock)

    model.begin_drag("Lead", 2)
    model.preview_to(0)
    restored = model.cancel()

    assert restored == ["EQ", "Compressor", "Limiter"]
    assert dock._channel_widgets["Lead"].insert_order == ["EQ", "Compressor", "Limiter"]
