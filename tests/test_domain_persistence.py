from pathlib import Path
from typing import Dict

import pytest

from domain.models import (
    InstrumentDefinition,
    InstrumentModule,
    Pattern,
    PatternStep,
    Project,
    ProjectMetadata,
)
from domain.persistence import ProjectFileAdapter, ProjectSerializer


@pytest.fixture()
def example_project(tmp_path: Path) -> Project:
    metadata = ProjectMetadata(id="proj", name="Example", bpm=140.0)
    project = Project(metadata=metadata)
    pattern = Pattern(
        id="pat",
        name="Intro",
        length_steps=4,
        steps=[PatternStep(note=60), PatternStep(note=62)],
    )
    instrument = InstrumentDefinition(
        id="inst",
        name="Lead",
        modules=[InstrumentModule(id="osc1", type="oscillator", parameters={"freq": 440.0})],
    )
    project.add_pattern(pattern)
    project.add_instrument(instrument)
    project.append_to_song(pattern.id)
    return project


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
