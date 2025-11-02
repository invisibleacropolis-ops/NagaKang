from pathlib import Path
from typing import Dict

import pytest

from domain.models import Project
from domain.persistence import ProjectFileAdapter, ProjectSerializer


def test_project_serializer_round_trip(example_project: Project):
    payload: Dict[str, object] = ProjectSerializer.to_dict(example_project)
    restored = ProjectSerializer.from_dict(payload)
    assert restored == example_project


def test_project_file_adapter_round_trip(tmp_path: Path, example_project: Project):
    adapter = ProjectFileAdapter(tmp_path)
    destination = adapter.save(example_project, "project.json")
    assert destination.exists()

    loaded = adapter.load("project.json")
    assert loaded == example_project
