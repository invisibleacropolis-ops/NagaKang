"""Pydantic-powered domain models for tracker projects.

These models graduate the Step 2 prototypes into a reusable package
that future steps can import from production code, CLI utilities, and
documentation examples. Each class mirrors the terminology defined in
the Comprehensive Development Plan while enforcing validation rules
for persistence and automation workflows.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class AutomationPoint(BaseModel):
    """Represents a normalized automation value at a point in musical time."""

    position_beats: float = Field(
        ..., ge=0.0, description="Position of the automation event in beats"
    )
    value: float = Field(..., description="Normalized value of the automation lane")


class PatternStep(BaseModel):
    """Single tracker grid step capable of optional note and per-step effects."""

    note: Optional[int] = Field(None, ge=0, le=127, description="MIDI note number or rest")
    velocity: Optional[int] = Field(100, ge=0, le=127, description="MIDI velocity")
    instrument_id: Optional[str] = Field(None, description="Instrument definition reference")
    step_effects: Dict[str, float] = Field(
        default_factory=dict, description="Tracker-style effect commands"
    )


class Pattern(BaseModel):
    """Collection of steps and automation lanes comprising a musical pattern."""

    id: str
    name: str
    length_steps: int = Field(..., gt=0)
    steps: List[PatternStep] = Field(default_factory=list)
    automation: Dict[str, List[AutomationPoint]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_steps_length(self) -> Pattern:  # type: ignore[override]
        if len(self.steps) > self.length_steps:
            raise ValueError("Pattern contains more steps than `length_steps`")
        return self

    @property
    def duration_beats(self) -> float:
        """Return the pattern duration in beats assuming 4 steps per beat."""

        return self.length_steps / 4.0


class InstrumentModule(BaseModel):
    """DSP building block referenced by instrument graphs."""

    id: str
    type: str
    parameters: Dict[str, float] = Field(default_factory=dict)
    inputs: List[str] = Field(default_factory=list)


class InstrumentDefinition(BaseModel):
    """Graph of modules that produce an instrument sound."""

    id: str
    name: str
    modules: List[InstrumentModule]
    macros: Dict[str, List[str]] = Field(default_factory=dict)


class ProjectMetadata(BaseModel):
    """Human-readable project metadata aligned with roadmap terminology."""

    id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bpm: float = Field(120.0, gt=0)
    swing: float = Field(0.0, ge=0.0, le=1.0)


class Project(BaseModel):
    """Top-level container storing patterns, instruments, and arrangement."""

    metadata: ProjectMetadata
    patterns: Dict[str, Pattern] = Field(default_factory=dict)
    instruments: Dict[str, InstrumentDefinition] = Field(default_factory=dict)
    song_order: List[str] = Field(
        default_factory=list, description="Ordered pattern IDs forming the arrangement"
    )

    def touch(self) -> None:
        """Update the modification timestamp."""

        self.metadata.updated_at = datetime.now(UTC)

    def add_pattern(self, pattern: Pattern) -> None:
        """Insert or replace a pattern while keeping timestamps accurate."""

        self.patterns[pattern.id] = pattern
        self.touch()

    def add_instrument(self, instrument: InstrumentDefinition) -> None:
        """Insert or replace an instrument while keeping timestamps accurate."""

        self.instruments[instrument.id] = instrument
        self.touch()

    def append_to_song(self, pattern_id: str) -> None:
        """Append a pattern to the arrangement, raising if the pattern is unknown."""

        if pattern_id not in self.patterns:
            raise KeyError(f"Pattern {pattern_id!r} not found")
        self.song_order.append(pattern_id)
        self.touch()

    def total_duration_beats(self) -> float:
        """Return the full arrangement length in beats."""

        return sum(self.patterns[pid].duration_beats for pid in self.song_order)
