from datetime import datetime

import pytest

from prototypes.domain_models import (
    AutomationPoint,
    InstrumentDefinition,
    InstrumentModule,
    Pattern,
    PatternStep,
    Project,
    ProjectMetadata,
)


def test_project_round_trip_updates_timestamp():
    metadata = ProjectMetadata(id="proj-1", name="Test Project", bpm=128.0)
    project = Project(metadata=metadata)
    before = project.metadata.updated_at

    pattern = Pattern(
        id="pat-1",
        name="Intro",
        length_steps=4,
        steps=[PatternStep(note=60), PatternStep(note=62)],
    )
    project.add_pattern(pattern)

    instrument = InstrumentDefinition(
        id="inst-1",
        name="Lead",
        modules=[InstrumentModule(id="osc", type="oscillator")],
    )
    project.add_instrument(instrument)
    project.append_to_song(pattern.id)

    assert project.song_order == ["pat-1"]
    assert project.patterns[pattern.id].name == "Intro"
    assert project.instruments[instrument.id].name == "Lead"
    assert project.metadata.updated_at >= before


def test_automation_point_validation():
    point = AutomationPoint(position_beats=1.5, value=0.75)
    assert pytest.approx(point.position_beats, 1e-6) == 1.5
    assert pytest.approx(point.value, 1e-6) == 0.75


@pytest.mark.parametrize(
    "bad_note",
    [-1, 128],
)
def test_pattern_step_note_bounds(bad_note):
    with pytest.raises(ValueError):
        PatternStep(note=bad_note)


def test_append_missing_pattern_raises():
    project = Project(metadata=ProjectMetadata(id="p", name="P"))
    with pytest.raises(KeyError):
        project.append_to_song("missing")


def test_touch_updates_timestamp():
    project = Project(metadata=ProjectMetadata(id="p", name="P"))
    before = project.metadata.updated_at
    project.touch()
    assert project.metadata.updated_at >= before
    assert isinstance(project.metadata.updated_at, datetime)
