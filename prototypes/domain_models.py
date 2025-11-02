"""Backward-compatible import shims for domain models.

The production-ready implementations now live under ``domain``.  This
module keeps legacy prototype imports functioning while documentation
and callers migrate to the new package.
"""
from __future__ import annotations

from domain.models import (
    AutomationPoint,
    InstrumentDefinition,
    InstrumentModule,
    Pattern,
    PatternStep,
    Project,
    ProjectMetadata,
)

__all__ = [
    "AutomationPoint",
    "InstrumentDefinition",
    "InstrumentModule",
    "Pattern",
    "PatternStep",
    "Project",
    "ProjectMetadata",
]
