"""Audio engine scaffolding focused on musician-friendly workflows."""
from .engine import (
    AutomationEvent,
    AutomationTimeline,
    EngineConfig,
    OfflineAudioEngine,
    ParameterSpec,
    TempoMap,
)
from .effects import SoftKneeCompressorInsert, ThreeBandEqInsert
from .mixer import (
    MixerChannel,
    MixerGraph,
    MixerReturnBus,
    MixerSendConfig,
    MixerSubgroup,
)
from .metrics import integrated_lufs, rms_dbfs, rms_per_channel
from .modules import AmplitudeEnvelope, ClipSampler, OnePoleLowPass, SineOscillator
from .tracker_bridge import (
    MixerPlaybackSnapshot,
    PatternPerformanceBridge,
    PatternPlayback,
)

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
    "MixerSubgroup",
    "AmplitudeEnvelope",
    "ClipSampler",
    "MixerPlaybackSnapshot",
    "PatternPerformanceBridge",
    "PatternPlayback",
    "OnePoleLowPass",
    "SineOscillator",
    "SoftKneeCompressorInsert",
    "ThreeBandEqInsert",
    "integrated_lufs",
    "rms_dbfs",
    "rms_per_channel",
]
