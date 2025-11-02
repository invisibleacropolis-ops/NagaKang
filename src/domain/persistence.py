"""Persistence helpers for reading and writing project documents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .models import Project


class ProjectSerializer:
    """Serialize :class:`Project` instances to/from JSON-compatible dicts."""

    @staticmethod
    def to_dict(project: Project) -> Dict[str, Any]:
        """Convert a project to a JSON-ready dictionary."""

        return project.model_dump(mode="json")

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> Project:
        """Rehydrate a project instance from serialized data."""

        return Project.model_validate(payload)


class ProjectFileAdapter:
    """Filesystem adapter that persists project documents under a base path."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def save(self, project: Project, filename: str) -> Path:
        """Write the project to ``base_path / filename`` and return the path."""

        destination = self.base_path / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(ProjectSerializer.to_dict(project), indent=2)
        destination.write_text(data, encoding="utf-8")
        return destination

    def load(self, filename: str) -> Project:
        """Load the project stored at ``base_path / filename``."""

        source = self.base_path / filename
        payload = json.loads(source.read_text(encoding="utf-8"))
        return ProjectSerializer.from_dict(payload)
