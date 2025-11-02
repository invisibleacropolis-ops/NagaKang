"""Repository abstractions for project persistence backends.

These interfaces layer on top of :mod:`domain.persistence` to support
both local filesystem storage and future cloud synchronisation targets
outlined in the Comprehensive Development Plan (README §2, §8). The
implementations here are intentionally lightweight yet fully tested so
subsequent steps can expand capabilities without breaking callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from pathlib import Path
from typing import Dict, Iterable, Protocol

from .models import Project
from .persistence import ProjectFileAdapter, ProjectSerializer


class ProjectRepositoryError(Exception):
    """Base error for repository failures."""


class ProjectNotFoundError(ProjectRepositoryError):
    """Raised when a requested project cannot be located."""


@dataclass(frozen=True)
class ProjectSummary:
    """Lightweight descriptor for enumerating stored projects."""

    identifier: str
    name: str
    updated_at: datetime
    location: str


class ProjectRepository(Protocol):
    """Minimal interface shared by local and remote repositories."""

    def save(self, project: Project) -> ProjectSummary:
        """Persist the project and return a :class:`ProjectSummary`."""

    def load(self, identifier: str) -> Project:
        """Retrieve a project by identifier."""

    def delete(self, identifier: str) -> None:
        """Remove the project from the backing store."""

    def list(self) -> Iterable[ProjectSummary]:
        """Iterate over available projects."""


class LocalProjectRepository(ProjectRepository):
    """Filesystem-backed repository using :class:`ProjectFileAdapter`."""

    def __init__(self, adapter: ProjectFileAdapter, *, extension: str = ".json") -> None:
        self._adapter = adapter
        self._extension = extension

    def _path_for(self, identifier: str) -> Path:
        return self._adapter.base_path / f"{identifier}{self._extension}"

    def save(self, project: Project) -> ProjectSummary:
        destination = self._adapter.save(project, f"{project.metadata.id}{self._extension}")
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location=str(destination),
        )

    def load(self, identifier: str) -> Project:
        path = self._path_for(identifier)
        if not path.exists():
            raise ProjectNotFoundError(f"Project {identifier!r} not found at {path}")
        return self._adapter.load(path.name)

    def delete(self, identifier: str) -> None:
        path = self._path_for(identifier)
        if not path.exists():
            raise ProjectNotFoundError(f"Project {identifier!r} not found at {path}")
        path.unlink()

    def list(self) -> Iterable[ProjectSummary]:
        for file_path in sorted(self._adapter.base_path.glob(f"*{self._extension}")):
            payload = self._adapter.load(file_path.name)
            yield ProjectSummary(
                identifier=payload.metadata.id,
                name=payload.metadata.name,
                updated_at=payload.metadata.updated_at,
                location=str(file_path),
            )


class InMemoryProjectRepository(ProjectRepository):
    """Dictionary-backed repository suitable for tests or mocked cloud storage."""

    def __init__(self) -> None:
        self._storage: Dict[str, Project] = {}

    def save(self, project: Project) -> ProjectSummary:
        self._storage[project.metadata.id] = project.model_copy(deep=True)
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location="in-memory",
        )

    def load(self, identifier: str) -> Project:
        try:
            project = self._storage[identifier]
        except KeyError as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in memory") from exc
        return project.model_copy(deep=True)

    def delete(self, identifier: str) -> None:
        if identifier not in self._storage:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in memory")
        del self._storage[identifier]

    def list(self) -> Iterable[ProjectSummary]:
        for project in self._storage.values():
            yield ProjectSummary(
                identifier=project.metadata.id,
                name=project.metadata.name,
                updated_at=project.metadata.updated_at,
                location="in-memory",
            )


class MockCloudProjectRepository(ProjectRepository):
    """Simulated cloud repository with naive sync + conflict detection.

    The adapter serializes payloads to a local cache so integration code can
    exercise round-trips without needing credentials. A small amount of
    artificial latency can be configured to mimic remote calls during tests.
    """

    def __init__(
        self,
        adapter: ProjectFileAdapter,
        *,
        bucket: str = "naga-cloud",
        extension: str = ".json",
        network_latency: float = 0.0,
    ) -> None:
        self._adapter = adapter
        self._bucket = bucket
        self._extension = extension
        self._network_latency = network_latency
        self._objects: Dict[str, Dict[str, object]] = {}
        self._revisions: Dict[str, datetime] = {}

    def _simulate_latency(self) -> None:
        if self._network_latency > 0.0:
            time.sleep(self._network_latency)

    def _path_for(self, identifier: str) -> Path:
        return self._adapter.base_path / f"{identifier}{self._extension}"

    def save(self, project: Project) -> ProjectSummary:
        previous_revision = self._revisions.get(project.metadata.id)
        if previous_revision and project.metadata.updated_at < previous_revision:
            raise ProjectRepositoryError(
                "Stale project metadata detected; update local state before saving"
            )
        self._simulate_latency()
        payload = ProjectSerializer.to_dict(project)
        self._objects[project.metadata.id] = payload
        self._revisions[project.metadata.id] = project.metadata.updated_at
        self._adapter.save(project, f"{project.metadata.id}{self._extension}")
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location=f"cloud://{self._bucket}/{project.metadata.id}",
        )

    def load(self, identifier: str) -> Project:
        self._simulate_latency()
        try:
            payload = self._objects[identifier]
        except KeyError as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in cloud store") from exc
        project = ProjectSerializer.from_dict(payload)  # type: ignore[arg-type]
        self._adapter.save(project, f"{identifier}{self._extension}")
        return project

    def delete(self, identifier: str) -> None:
        self._simulate_latency()
        if identifier not in self._objects:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in cloud store")
        del self._objects[identifier]
        self._revisions.pop(identifier, None)
        cache_path = self._path_for(identifier)
        if cache_path.exists():
            cache_path.unlink()

    def list(self) -> Iterable[ProjectSummary]:
        self._simulate_latency()
        for identifier, payload in sorted(self._objects.items()):
            project = ProjectSerializer.from_dict(payload)  # type: ignore[arg-type]
            yield ProjectSummary(
                identifier=identifier,
                name=project.metadata.name,
                updated_at=project.metadata.updated_at,
                location=f"cloud://{self._bucket}/{identifier}",
            )
