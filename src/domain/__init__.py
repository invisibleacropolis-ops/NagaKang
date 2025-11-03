"""Domain package exposing tracker data models and persistence helpers."""
from .models import (
    AutomationPoint,
    InstrumentDefinition,
    InstrumentModule,
    Pattern,
    PatternStep,
    Project,
    ProjectMetadata,
)
from .persistence import ProjectFileAdapter, ProjectSerializer
from .repository import (
    InMemoryProjectRepository,
    LocalProjectRepository,
    ProjectNotFoundError,
    ProjectRepository,
    ProjectRepositoryError,
    ProjectSummary,
    S3ProjectRepository,
)

__all__ = [
    "AutomationPoint",
    "InstrumentDefinition",
    "InstrumentModule",
    "Pattern",
    "PatternStep",
    "Project", 
    "ProjectMetadata",
    "ProjectFileAdapter",
    "ProjectSerializer",
    "ProjectRepository",
    "LocalProjectRepository",
    "InMemoryProjectRepository",
    "S3ProjectRepository",
    "ProjectSummary",
    "ProjectRepositoryError",
    "ProjectNotFoundError",
]
