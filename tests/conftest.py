import sys
from pathlib import Path

import pytest

from domain.models import (
    InstrumentDefinition,
    InstrumentModule,
    Pattern,
    PatternStep,
    Project,
    ProjectMetadata,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def example_project() -> Project:
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
