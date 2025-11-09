"""Audio engine scaffolding focused on musician-friendly workflows."""
from .engine import (
    AutomationEvent,
    AutomationTimeline,
    EngineConfig,
    OfflineAudioEngine,
    ParameterSpec,
    TempoMap,
)
from .mixer import MixerChannel, MixerGraph, MixerReturnBus, MixerSendConfig
from .metrics import integrated_lufs, rms_dbfs, rms_per_channel
from .modules import AmplitudeEnvelope, ClipSampler, OnePoleLowPass, SineOscillator
from .tracker_bridge import PatternPerformanceBridge, PatternPlayback

__all__ = [
    "AutomationEvent",
    "AutomationTimeline",
    "EngineConfig",
    "OfflineAudioEngine",
    "ParameterSpec",
    "TempoMap",
    "MixerChannel",
    "MixerGraph",
    "MixerReturnBus",
    "MixerSendConfig",
    "AmplitudeEnvelope",
    "ClipSampler",
    "PatternPerformanceBridge",
    "PatternPlayback",
    "OnePoleLowPass",
    "SineOscillator",
    "integrated_lufs",
    "rms_dbfs",
    "rms_per_channel",
]
