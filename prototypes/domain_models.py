"""Domain model scaffolding aligned with Step 2 planning."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional

try:
    from pydantic import BaseModel, Field, model_validator
except ImportError as exc:  # pragma: no cover - ensures informative failure
    raise RuntimeError(
        "pydantic is required to use the domain model prototypes. Install it via `pip install pydantic`."
    ) from exc


class AutomationPoint(BaseModel):
    position_beats: float = Field(..., ge=0.0, description="Position of the automation event in beats")
    value: float = Field(..., description="Normalized value of the automation lane at the specified beat")


class PatternStep(BaseModel):
    note: Optional[int] = Field(None, ge=0, le=127, description="MIDI note number or None for rest")
    velocity: Optional[int] = Field(100, ge=0, le=127, description="MIDI velocity")
    instrument_id: Optional[str] = Field(None, description="Reference to instrument definition")
    step_effects: Dict[str, float] = Field(default_factory=dict, description="Tracker-style effect commands")


class Pattern(BaseModel):
    id: str
    name: str
    length_steps: int = Field(..., gt=0)
    steps: List[PatternStep] = Field(default_factory=list)
    automation: Dict[str, List[AutomationPoint]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_steps_length(self):
        if len(self.steps) > self.length_steps:
            raise ValueError("Pattern contains more steps than `length_steps`")
        return self


class InstrumentModule(BaseModel):
    id: str
    type: str
    parameters: Dict[str, float] = Field(default_factory=dict)
    inputs: List[str] = Field(default_factory=list)


class InstrumentDefinition(BaseModel):
    id: str
    name: str
    modules: List[InstrumentModule]
    macros: Dict[str, List[str]] = Field(default_factory=dict)


class ProjectMetadata(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bpm: float = Field(120.0, gt=0)
    swing: float = Field(0.0, ge=0.0, le=1.0)


class Project(BaseModel):
    metadata: ProjectMetadata
    patterns: Dict[str, Pattern] = Field(default_factory=dict)
    instruments: Dict[str, InstrumentDefinition] = Field(default_factory=dict)
    song_order: List[str] = Field(default_factory=list, description="Ordered pattern IDs forming the arrangement")

    def touch(self) -> None:
        """Update modification timestamp."""
        self.metadata.updated_at = datetime.now(UTC)

    def add_pattern(self, pattern: Pattern) -> None:
        self.patterns[pattern.id] = pattern
        self.touch()

    def add_instrument(self, instrument: InstrumentDefinition) -> None:
        self.instruments[instrument.id] = instrument
        self.touch()

    def append_to_song(self, pattern_id: str) -> None:
        if pattern_id not in self.patterns:
            raise KeyError(f"Pattern {pattern_id!r} not found")
        self.song_order.append(pattern_id)
        self.touch()
