from audio.mixer import MeterReading

from gui.mixer_board import MixerDockWidget, MixerStripState
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
