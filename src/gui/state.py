"""Dataclasses describing tracker/mixer panel state for the GUI shell."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from audio.mixer import MeterReading

from .mixer_board import MixerStripState


@dataclass
class TrackerPanelState:
    """State bundle rendered into the tracker-side widgets."""

    pattern_id: str
    pending_requests: List[Dict[str, object]] = field(default_factory=list)
    last_preview_summary: Dict[str, object] | None = None
    loudness_rows: List[Dict[str, object]] = field(default_factory=list)


@dataclass
class MixerPanelState:
    """State bundle rendered into the mixer widgets."""

    strip_states: Dict[str, MixerStripState] = field(default_factory=dict)
    return_states: Dict[str, MixerStripState] = field(default_factory=dict)
    master_meter: MeterReading | None = None


@dataclass
class TrackerMixerLayoutState:
    """High-level view model driving the Step 7 layout shell."""

    tracker: TrackerPanelState
    mixer: MixerPanelState
