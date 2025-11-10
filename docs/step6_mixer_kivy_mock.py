"""Kivy prototype bridging Step 6 mixer primitives to a touch mock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

from audio.effects import PlateReverbInsert, StereoFeedbackDelayInsert
from audio.engine import BaseAudioModule, EngineConfig
from audio.mixer import (
    MeterReading,
    MixerChannel,
    MixerGraph,
    MixerReturnBus,
    MixerSendConfig,
    MixerSubgroup,
)

try:  # pragma: no cover - Kivy is optional for documentation builds
    from kivy.properties import BooleanProperty, DictProperty, ListProperty, NumericProperty, StringProperty
    from kivy.uix.boxlayout import BoxLayout
except Exception:  # pragma: no cover - fallback keeps type checkers happy
    class BoxLayout:  # type: ignore
        def __init__(self, **kwargs) -> None:  # pragma: no cover - fallback
            super().__init__()

    def BooleanProperty(default=False):  # type: ignore
        return bool(default)

    def NumericProperty(default=0.0):  # type: ignore
        return default

    def StringProperty(default=""):  # type: ignore
        return default

    def DictProperty(default=None):  # type: ignore
        return {} if default is None else dict(default)

    def ListProperty(default=None):  # type: ignore
        return list(default or [])


@dataclass
class MixerStripState:
    """Plain-data bridge the Kivy mock uses to hydrate strip widgets."""

    name: str
    fader_db: float
    pan: float
    subgroup_meter: MeterReading
    sends: Mapping[str, float]
    insert_order: List[str]
    is_return: bool = False


class MixerStripWidget(BoxLayout):
    """Minimal Kivy widget mirroring the tracker-style mixer strip layout."""

    strip_name = StringProperty("--")
    meter_peak_db = NumericProperty(-120.0)
    meter_rms_db = NumericProperty(-120.0)
    send_levels = DictProperty({})
    insert_order = ListProperty([])
    is_return = BooleanProperty(False)

    def apply_state(self, state: MixerStripState) -> None:
        self.strip_name = state.name
        self.meter_peak_db = state.subgroup_meter.peak_db
        self.meter_rms_db = state.subgroup_meter.rms_db
        self.send_levels = dict(state.sends)
        self.insert_order = list(state.insert_order)
        self.is_return = bool(state.is_return)


class MixerBoardAdapter:
    """View-model translating :class:`MixerGraph` state for Kivy mocks."""

    def __init__(self, graph: MixerGraph) -> None:
        self._graph = graph

    def strip_state(self, channel_name: str) -> MixerStripState:
        channel = self._graph.channels[channel_name]
        subgroup_name = self._graph.channel_groups.get(channel_name)
        if subgroup_name is not None:
            meter = self._graph.subgroup_meters.get(
                subgroup_name, MeterReading(-float("inf"), -float("inf"))
            )
        else:
            meter = MeterReading(-float("inf"), -float("inf"))
        sends: Dict[str, float] = {}
        for send in channel._sends.values():  # pragma: no cover - doc helper
            sends[send.bus] = send.level_db
        insert_order: List[str] = []
        for processor in getattr(channel, "_inserts", []):  # pragma: no cover - doc helper
            label = getattr(processor, "__name__", processor.__class__.__name__)
            insert_order.append(label or "Insert")
        return MixerStripState(
            name=channel.name,
            fader_db=channel.fader_db,
            pan=channel.pan,
            subgroup_meter=meter,
            sends=sends,
            insert_order=insert_order,
            is_return=False,
        )

    def bind_to_widget(self, widget: MixerStripWidget, channel_name: str) -> None:
        widget.apply_state(self.strip_state(channel_name))

    def return_state(self, bus_name: str) -> MixerStripState:
        bus = self._graph.returns[bus_name]
        processor = getattr(bus, "_processor", None)
        processor_label = "Bypass"
        if processor is not None:
            processor_label = getattr(processor, "__name__", processor.__class__.__name__)
        return MixerStripState(
            name=bus.name,
            fader_db=getattr(bus, "level_db", 0.0),
            pan=0.0,
            subgroup_meter=MeterReading(-float("inf"), -float("inf")),
            sends={},
            insert_order=[processor_label],
            is_return=True,
        )

    def reorder_channel_inserts(self, channel_name: str, from_index: int, to_index: int) -> None:
        channel = self._graph.channels[channel_name]
        channel.move_insert(from_index, to_index)


def build_demo_graph() -> MixerGraph:
    """Assemble a demo mixer showcasing the new Step 6 routing features."""

    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    graph = MixerGraph(config)

    drums = MixerSubgroup("drums", config=config, fader_db=-3.0)
    band = MixerSubgroup("band", config=config)
    graph.add_subgroup(drums)
    graph.add_subgroup(band)
    graph.assign_subgroup_to_group("drums", "band")

    drum_bus = MixerReturnBus(
        "drum_room",
        processor=PlateReverbInsert(config, mix=0.5, decay=0.7),
        level_db=-6.0,
    )
    vox_delay = MixerReturnBus(
        "vox_delay",
        processor=StereoFeedbackDelayInsert(config, delay_ms=220.0, feedback=0.45),
        level_db=-9.0,
    )
    graph.add_return_bus(drum_bus)
    graph.add_return_bus(vox_delay)

    class ConstantModule(BaseAudioModule):
        def __init__(self, name: str, config: EngineConfig, value: float) -> None:
            super().__init__(name, config, [])
            self._value = value

        def process(self, frames: int):  # pragma: no cover - doc helper
            import numpy as np

            return np.full((frames, self.config.channels), self._value, dtype=np.float32)

    kick_src = ConstantModule("kick_src", config, value=0.8)
    vox_src = ConstantModule("vox_src", config, value=0.5)

    kick = MixerChannel(
        "Kick",
        source=kick_src,
        config=config,
        sends=[MixerSendConfig(bus="drum_room", level_db=-8.0)],
    )
    vox = MixerChannel(
        "Vocals",
        source=vox_src,
        config=config,
        sends=[
            MixerSendConfig(bus="drum_room", level_db=-20.0),
            MixerSendConfig(bus="vox_delay", level_db=-12.0, pre_fader=False),
        ],
    )
    graph.add_channel(kick)
    graph.add_channel(vox)
    graph.assign_channel_to_group("Kick", "drums")
    graph.assign_channel_to_group("Vocals", "band")

    # Prime meters for UI binding.
    graph.process_block(config.block_size)
    return graph


__all__ = [
    "MixerBoardAdapter",
    "MixerStripState",
    "MixerStripWidget",
    "build_demo_graph",
]
