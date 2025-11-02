from pathlib import Path

import pytest

from domain.models import Project
from domain.persistence import ProjectFileAdapter
from domain.repository import (
    InMemoryProjectRepository,
    LocalProjectRepository,
    ProjectNotFoundError,
    ProjectSummary,
)


def _assert_summary(summary: ProjectSummary, project: Project) -> None:
    assert summary.identifier == project.metadata.id
    assert summary.name == project.metadata.name
    assert summary.updated_at == project.metadata.updated_at


def test_local_repository_round_trip(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    repo = LocalProjectRepository(adapter)

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)
    assert Path(summary.location).exists()

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    listed = list(repo.list())
    assert len(listed) == 1
    _assert_summary(listed[0], example_project)


def test_local_repository_missing_project(tmp_path: Path) -> None:
    repo = LocalProjectRepository(ProjectFileAdapter(tmp_path))

    with pytest.raises(ProjectNotFoundError):
        repo.load("missing")

    with pytest.raises(ProjectNotFoundError):
        repo.delete("missing")


def test_in_memory_repository_behaves_like_remote(example_project: Project) -> None:
    repo = InMemoryProjectRepository()

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    repo.delete(example_project.metadata.id)

    with pytest.raises(ProjectNotFoundError):
        repo.load(example_project.metadata.id)

