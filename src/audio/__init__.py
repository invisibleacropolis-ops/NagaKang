"""Audio engine scaffolding focused on musician-friendly workflows."""
from .engine import (
    AutomationEvent,
    AutomationTimeline,
    EngineConfig,
    OfflineAudioEngine,
    ParameterSpec,
    TempoMap,
)
from .modules import SineOscillator

__all__ = [
    "AutomationEvent",
    "AutomationTimeline",
    "EngineConfig",
    "OfflineAudioEngine",
    "ParameterSpec",
    "TempoMap",
    "SineOscillator",
]
