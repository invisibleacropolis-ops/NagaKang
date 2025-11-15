"""Mixer board adapter and widgets shared by the Step 7 GUI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, MutableMapping, TYPE_CHECKING, Type

from audio.mixer import MeterReading, MixerGraph

try:  # pragma: no cover - optional dependency for docs and runtime shell
    from kivy.properties import BooleanProperty, DictProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
    from kivy.uix.boxlayout import BoxLayout
except Exception:  # pragma: no cover - fallback keeps type checkers and tests happy
    class BoxLayout:  # type: ignore
        """Minimal stand-in when Kivy is unavailable (e.g., CI)."""

        def __init__(self, **kwargs) -> None:  # pragma: no cover - trivial
            super().__init__()
            self.children: List[object] = []
            self.orientation = kwargs.get("orientation", "horizontal")

        def add_widget(self, widget) -> None:  # pragma: no cover - fallback helper
            self.children.append(widget)

        def remove_widget(self, widget) -> None:  # pragma: no cover - fallback helper
            if widget in self.children:
                self.children.remove(widget)

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

    def ObjectProperty(default=None):  # type: ignore
        return default


if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from .state import MixerPanelState


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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._insert_reorder_callback: Callable[[int, int], List[str]] | None = None

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

    # ------------------------------------------------------------------
    # Gesture hooks
    # ------------------------------------------------------------------
    def bind_reorder_callback(self, callback: Callable[[int, int], List[str]] | None) -> None:
        """Register a callback that handles insert drag/reorder gestures."""

        self._insert_reorder_callback = callback

    def request_insert_reorder(self, from_index: int, to_index: int) -> List[str]:
        """Trigger insert reordering and mirror the updated order locally."""

        if self._insert_reorder_callback is None:
            raise RuntimeError("Insert reorder callback has not been bound")
        updated_order = self._insert_reorder_callback(from_index, to_index)
        self.insert_order = list(updated_order)
        return list(self.insert_order)


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


class MixerDockWidget(BoxLayout):
    """Container widget that mirrors mixer panel state for the layout shell."""

    master_peak_db = NumericProperty(-120.0)
    master_rms_db = NumericProperty(-120.0)
    strip_container = ObjectProperty(None)
    return_container = ObjectProperty(None)
    controller = ObjectProperty(None)

    def __init__(
        self,
        *,
        strip_factory: Type[MixerStripWidget] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if getattr(self, "orientation", None) is None:
            self.orientation = "horizontal"
        self._strip_factory = strip_factory or MixerStripWidget
        self._channel_widgets: MutableMapping[str, MixerStripWidget] = {}
        self._return_widgets: MutableMapping[str, MixerStripWidget] = {}
        self.strip_container = self._build_container()
        self.return_container = self._build_container()
        self.add_widget(self.strip_container)
        self.add_widget(self.return_container)
        self._controller: MixerDockController | None = None

    def _build_container(self) -> BoxLayout:
        return BoxLayout(orientation="vertical")

    def bind_controller(self, controller: "MixerDockController") -> None:
        """Attach a controller that executes insert and return gestures."""

        self._controller = controller
        self.controller = controller
        for name, widget in self._channel_widgets.items():
            self._attach_reorder_callback(name, widget)

    def apply_state(self, state: "MixerPanelState") -> None:
        self._sync_widgets(state.strip_states, self._channel_widgets, self.strip_container, is_return=False)
        self._sync_widgets(state.return_states, self._return_widgets, self.return_container, is_return=True)
        if state.master_meter is None:
            self.master_peak_db = -float("inf")
            self.master_rms_db = -float("inf")
        else:
            self.master_peak_db = state.master_meter.peak_db
            self.master_rms_db = state.master_meter.rms_db

    def request_insert_reorder(self, channel_name: str, from_index: int, to_index: int) -> List[str]:
        """Proxy reorder gestures from KV bindings into the controller."""

        if self._controller is None:
            raise RuntimeError("MixerDockController has not been bound")
        new_state = self._controller.reorder_inserts(channel_name, from_index, to_index)
        widget = self._channel_widgets.get(channel_name)
        if widget is not None:
            widget.apply_state(new_state)
        return list(new_state.insert_order)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _sync_widgets(
        self,
        states: Mapping[str, MixerStripState],
        widgets: MutableMapping[str, MixerStripWidget],
        container: BoxLayout,
        *,
        is_return: bool,
    ) -> None:
        seen = set()
        for name, strip_state in states.items():
            seen.add(name)
            widget = widgets.get(name)
            if widget is None:
                widget = self._strip_factory()
                widgets[name] = widget
                if hasattr(container, "add_widget"):
                    container.add_widget(widget)
                if not is_return:
                    self._attach_reorder_callback(name, widget)
            widget.apply_state(strip_state)
        for name in list(widgets):
            if name not in seen:
                widget = widgets.pop(name)
                if not is_return:
                    self._detach_reorder_callback(widget)
                if hasattr(container, "remove_widget"):
                    container.remove_widget(widget)

    def _attach_reorder_callback(self, channel_name: str, widget: MixerStripWidget) -> None:
        if not hasattr(widget, "bind_reorder_callback"):
            return
        if self._controller is None:
            widget.bind_reorder_callback(None)
            return

        def _handler(from_index: int, to_index: int) -> List[str]:
            return self.request_insert_reorder(channel_name, from_index, to_index)

        widget.bind_reorder_callback(_handler)

    def _detach_reorder_callback(self, widget: MixerStripWidget) -> None:
        if hasattr(widget, "bind_reorder_callback"):
            widget.bind_reorder_callback(None)


class MixerDockController:
    """Controller forwarding dock gestures to :class:`MixerBoardAdapter`."""

    def __init__(self, adapter: MixerBoardAdapter) -> None:
        self._adapter = adapter

    def reorder_inserts(self, channel_name: str, from_index: int, to_index: int) -> MixerStripState:
        self._adapter.reorder_channel_inserts(channel_name, from_index, to_index)
        return self._adapter.strip_state(channel_name)
