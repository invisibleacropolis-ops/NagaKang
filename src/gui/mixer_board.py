"""Mixer board adapter and widgets shared by the Step 7 GUI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

from audio.mixer import MeterReading, MixerGraph

try:  # pragma: no cover - optional dependency for docs and runtime shell
    from kivy.properties import BooleanProperty, DictProperty, ListProperty, NumericProperty, StringProperty
    from kivy.uix.boxlayout import BoxLayout
except Exception:  # pragma: no cover - fallback keeps type checkers and tests happy
    class BoxLayout:  # type: ignore
        """Minimal stand-in when Kivy is unavailable (e.g., CI)."""

        def __init__(self, **_kwargs) -> None:  # pragma: no cover - trivial
            super().__init__()

    def BooleanProperty(default: bool = False):  # type: ignore
        return bool(default)

    def NumericProperty(default: float = 0.0):  # type: ignore
        return float(default)

    def StringProperty(default: str = ""):
        return default

    def DictProperty(default=None):  # type: ignore
        return {} if default is None else dict(default)

    def ListProperty(default=None):  # type: ignore
        return list(default or [])


@dataclass
class MixerStripState:
    """Plain-data representation used to hydrate strip widgets."""

    name: str
    fader_db: float
    pan: float
    post_fader_meter: MeterReading
    subgroup_meter: MeterReading | None
    sends: Mapping[str, float]
    insert_order: List[str]
    is_return: bool = False
    return_level_db: float | None = None


class MixerStripWidget(BoxLayout):
    """Minimal Kivy widget mirroring the tracker-style mixer strip layout."""

    strip_name = StringProperty("--")
    meter_peak_db = NumericProperty(-120.0)
    meter_rms_db = NumericProperty(-120.0)
    subgroup_peak_db = NumericProperty(-120.0)
    subgroup_rms_db = NumericProperty(-120.0)
    send_levels = DictProperty({})
    insert_order = ListProperty([])
    is_return = BooleanProperty(False)
    return_level_db = NumericProperty(0.0)

    def apply_state(self, state: MixerStripState) -> None:
        self.strip_name = state.name
        self.meter_peak_db = state.post_fader_meter.peak_db
        self.meter_rms_db = state.post_fader_meter.rms_db
        subgroup_meter = state.subgroup_meter or MeterReading(-float("inf"), -float("inf"))
        self.subgroup_peak_db = subgroup_meter.peak_db
        self.subgroup_rms_db = subgroup_meter.rms_db
        self.send_levels = dict(state.sends)
        self.insert_order = list(state.insert_order)
        self.is_return = bool(state.is_return)
        self.return_level_db = float(state.return_level_db or 0.0)

    def update_post_meter(self, meter: MeterReading) -> None:
        self.meter_peak_db = meter.peak_db
        self.meter_rms_db = meter.rms_db

    def update_subgroup_meter(self, meter: MeterReading | None) -> None:
        if meter is None:
            meter = MeterReading(-float("inf"), -float("inf"))
        self.subgroup_peak_db = meter.peak_db
        self.subgroup_rms_db = meter.rms_db


class MixerBoardAdapter:
    """View-model translating :class:`MixerGraph` state for the GUI shell."""

    def __init__(self, graph: MixerGraph) -> None:
        self._graph = graph

    @property
    def graph(self) -> MixerGraph:
        return self._graph

    def channel_names(self) -> List[str]:
        return list(self._graph.channels.keys())

    def return_names(self) -> List[str]:
        return list(self._graph.returns.keys())

    def strip_state(self, channel_name: str) -> MixerStripState:
        channel = self._graph.channels[channel_name]
        subgroup_name = self._graph.channel_groups.get(channel_name)
        subgroup_meter = None
        if subgroup_name is not None:
            subgroup_meter = self._graph.subgroup_meters.get(
                subgroup_name, MeterReading(-float("inf"), -float("inf"))
            )
        sends: Dict[str, float] = {}
        for send in getattr(channel, "_sends", {}).values():  # pragma: no cover - view helper
            sends[send.bus] = send.level_db
        insert_order: List[str] = []
        for processor in getattr(channel, "_inserts", []):  # pragma: no cover - view helper
            label = getattr(processor, "__name__", processor.__class__.__name__)
            insert_order.append(label or "Insert")
        return MixerStripState(
            name=channel.name,
            fader_db=channel.fader_db,
            pan=channel.pan,
            post_fader_meter=self._graph.channel_post_meters.get(
                channel_name, MeterReading(-float("inf"), -float("inf"))
            ),
            subgroup_meter=subgroup_meter,
            sends=sends,
            insert_order=insert_order,
            is_return=False,
        )

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
            post_fader_meter=MeterReading(-float("inf"), -float("inf")),
            subgroup_meter=None,
            sends={},
            insert_order=[processor_label],
            is_return=True,
            return_level_db=bus.level_db,
        )

    def bind_to_widget(self, widget: MixerStripWidget, channel_name: str) -> None:
        widget.apply_state(self.strip_state(channel_name))

    def bind_return_to_widget(self, widget: MixerStripWidget, bus_name: str) -> None:
        widget.apply_state(self.return_state(bus_name))

    def reorder_channel_inserts(self, channel_name: str, from_index: int, to_index: int) -> None:
        channel = self._graph.channels[channel_name]
        channel.move_insert(from_index, to_index)

    def set_return_level(self, bus_name: str, level_db: float) -> None:
        bus = self._graph.returns[bus_name]
        bus.set_level_db(level_db)

    def update_channel_meter(self, widget: MixerStripWidget, channel_name: str) -> None:
        subgroup_name = self._graph.channel_groups.get(channel_name)
        meter = None
        if subgroup_name is not None:
            meter = self._graph.subgroup_meters.get(subgroup_name)
        widget.update_post_meter(
            self._graph.channel_post_meters.get(
                channel_name, MeterReading(-float("inf"), -float("inf"))
            )
        )
        widget.update_subgroup_meter(meter)

    def master_meter(self) -> MeterReading:
        return self._graph.master_meter
