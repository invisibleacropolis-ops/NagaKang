"""Audio engine scaffolding focused on musician-friendly workflows."""
from .engine import (
    AutomationEvent,
    AutomationTimeline,
    EngineConfig,
    OfflineAudioEngine,
    ParameterSpec,
    TempoMap,
)
from .metrics import integrated_lufs, rms_dbfs, rms_per_channel
from .modules import AmplitudeEnvelope, OnePoleLowPass, SineOscillator

__all__ = [
    "AutomationEvent",
    "AutomationTimeline",
    "EngineConfig",
    "OfflineAudioEngine",
    "ParameterSpec",
    "TempoMap",
    "AmplitudeEnvelope",
    "OnePoleLowPass",
    "SineOscillator",
    "integrated_lufs",
    "rms_dbfs",
    "rms_per_channel",
]
