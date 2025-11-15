"""Dataclasses describing tracker/mixer panel state for the GUI shell."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Sequence

from audio.mixer import MeterReading

from .mixer_board import MixerStripState


@dataclass
class TrackerPanelState:
    """State bundle rendered into the tracker-side widgets."""

    pattern_id: str
    pending_requests: List[Dict[str, object]] = field(default_factory=list)
    last_preview_summary: Dict[str, object] | None = None
    loudness_rows: List[Dict[str, object]] = field(default_factory=list)
    tempo_bpm: float = 120.0
    is_playing: bool = False
    loop_window_steps: float = 16.0
    tutorial_tips: List[str] = field(default_factory=list)
    import_dialog_filters: List[Mapping[str, Sequence[str]]] = field(default_factory=list)
    import_asset_count: int = 0
    autosave_recovery_prompt: str | None = None
    import_manifest_sha256: str | None = None
    import_bundle_root: str | None = None
    import_sampler_asset_names: List[str] = field(default_factory=list)


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
