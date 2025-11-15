from __future__ import annotations

import pytest

import json

from audio.engine import EngineConfig, TempoMap
from audio.mixer import MeterReading, MixerChannel, MixerGraph
from audio.modules import SineOscillator
from audio.tracker_bridge import PatternPerformanceBridge
from domain.models import InstrumentDefinition, InstrumentModule, Pattern, PatternStep
from typing import cast

from domain.project_manifest import SamplerManifestIndex, compute_file_sha256

from gui.app import TrackerMixerRoot
from gui.mixer_board import MixerBoardAdapter, MixerDockController, MixerStripState
from gui.preview import PreviewBatchState, PreviewOrchestrator
from gui.state import MixerPanelState, TrackerMixerLayoutState, TrackerPanelState
from gui.tracker_panel import TrackerPanelController
from tracker.pattern_editor import PatternEditor
from tracker.preview_service import MutationPreviewService
from tracker.playback_worker import PlaybackWorker


def build_instrument() -> InstrumentDefinition:
    return InstrumentDefinition(
        id="lead",
        name="Lead",
        modules=[
            InstrumentModule(id="osc", type="sine"),
            InstrumentModule(id="env", type="amplitude_envelope", inputs=["osc"]),
        ],
        macros={"mixer_channel": ["lead"]},
    )


def test_preview_orchestrator_emits_layout_state() -> None:
    instrument = build_instrument()
    pattern = Pattern(
        id="pattern_A",
        name="Pattern A",
        length_steps=16,
        steps=[PatternStep() for _ in range(16)],
    )
    editor = PatternEditor(pattern)
    service = MutationPreviewService(editor)
    editor.set_step(0, note=60, velocity=110, instrument_id=instrument.id)
    service.enqueue_mutation(editor.history[-1])

    config = EngineConfig(sample_rate=8_000, block_size=64, channels=2)
    tempo = TempoMap(tempo_bpm=100.0)
    mixer = MixerGraph(config)
    dummy_source = SineOscillator("preview_source", config)
    mixer.add_channel(MixerChannel("lead", source=dummy_source, config=config))

    bridge = PatternPerformanceBridge(config, tempo, mixer=mixer)
    worker = PlaybackWorker(
        service,
        bridge=bridge,
        instruments={instrument.id: instrument},
        default_instrument_id=instrument.id,
    )

    adapter = MixerBoardAdapter(mixer)
    orchestrator = PreviewOrchestrator(
        worker,
        mixer_adapter=adapter,
        loudness_provider=lambda playback, beats: bridge.tracker_loudness_rows(
            playback, beats_per_bucket=beats
        ),
        tempo_bpm=tempo.tempo_bpm,
        loop_window_steps=8.0,
        tutorial_tips=["Custom tip", "Secondary hint"],
    )

    batch = orchestrator.process_pending()

    assert batch.previews, "Expected at least one preview render"
    layout = batch.layout
    assert layout.tracker.pattern_id == pattern.id
    assert layout.tracker.pending_requests, "Tracker summary should describe processed mutation"
    assert layout.tracker.loudness_rows, "Loudness rows should be generated via the bridge helper"
    assert layout.tracker.tempo_bpm == pytest.approx(tempo.tempo_bpm)
    assert layout.tracker.loop_window_steps == pytest.approx(8.0)
    assert layout.tracker.tutorial_tips[0] == "Custom tip"
    assert "lead" in layout.mixer.strip_states
    assert layout.mixer.master_meter is not None


def test_tracker_mixer_root_binds_orchestrator() -> None:
    pattern = Pattern(
        id="pattern_B",
        name="Pattern B",
        length_steps=8,
        steps=[PatternStep() for _ in range(8)],
    )
    editor = PatternEditor(pattern)
    editor.set_step(0, note=64, velocity=90, instrument_id="lead")
    service = MutationPreviewService(editor)
    controller = TrackerPanelController(service)
    class DummyDockController:
        def __init__(self) -> None:
            self.reorder_calls: list[tuple[str, int, int]] = []

        def reorder_inserts(self, channel_name: str, from_index: int, to_index: int) -> MixerStripState:
            self.reorder_calls.append((channel_name, from_index, to_index))
            return mixer_state.strip_states[channel_name]

    dock_controller = cast(MixerDockController, DummyDockController())
    tracker_state = TrackerPanelState(
        pattern_id=pattern.id,
        tempo_bpm=140.0,
        loop_window_steps=2.0,
        tutorial_tips=["Loop the intro fill"],
    )
    mixer_state = MixerPanelState(
        strip_states={
            "Lead": MixerStripState(
                name="Lead",
                fader_db=-3.0,
                pan=0.0,
                post_fader_meter=MeterReading(-6.0, -9.0),
                subgroup_meter=None,
                sends={},
                insert_order=[],
            )
        },
        master_meter=MeterReading(-1.0, -4.0),
    )
    layout = TrackerMixerLayoutState(
        tracker=tracker_state,
        mixer=mixer_state,
    )
    batch = PreviewBatchState(layout=layout, previews=[])

    class DummyOrchestrator:
        def __init__(self) -> None:
            self.calls = 0

        def process_pending(self) -> PreviewBatchState:
            self.calls += 1
            return batch

    orchestrator = DummyOrchestrator()
    root = TrackerMixerRoot(tracker_controller=controller, mixer_controller=dock_controller)
    root.bind_orchestrator(orchestrator, interval=0.0)

    root._poll_orchestrator()

    assert root.layout_state is layout
    assert orchestrator.calls == 1
    assert root.transport_controls.loop_window_steps == pytest.approx(2.0)
    assert root.tracker_grid.pattern_id == pattern.id
    assert not service.queue
    assert root.mixer_dock.master_peak_db == pytest.approx(-1.0)
    assert root.mixer_dock.strip_container.children
    root.mixer_dock.request_insert_reorder("Lead", 0, 0)
    assert dock_controller.reorder_calls == [("Lead", 0, 0)]

    playback_requests = root.transport_controls.start_playback()

    assert playback_requests, "Transport start should enqueue loop previews"
    assert len(service.queue) == len(playback_requests)
    assert root.transport_controls.is_playing is True


def test_tracker_mixer_root_import_plan_and_autosave(tmp_path) -> None:
    tracker_state = TrackerPanelState(pattern_id="demo")
    layout = TrackerMixerLayoutState(tracker=tracker_state, mixer=MixerPanelState())
    batch = PreviewBatchState(layout=layout, previews=[])

    manifest_payload = {
        "bucket": "demo",
        "prefix": "velocity/",
        "last_updated": "2025-11-25T00:00:00+00:00",
        "assets": [
            {"name": "choir.wav", "sha256": "04ae3180a3ec59f52f4801f2b86c2d58196fa9dc78b86a51003da6778cbad09b"}
        ],
    }
    manifest_index = SamplerManifestIndex.from_payload(manifest_payload)
    manifest_path = tmp_path / "project_manifest.json"
    manifest_path.write_text("{\n  \"manifest_version\": \"1.0.0\"\n}", encoding="utf-8")

    root = TrackerMixerRoot()
    root.configure_sampler_manifest(manifest_index, manifest_path=manifest_path)

    time_values = iter([0.0, 2.0, 4.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:  # pragma: no cover - defensive guard
            return 10.0

    autosave_root = tmp_path / ".autosave"
    root.enable_autosave(
        project_id="demo",
        autosave_dir=autosave_root,
        interval_seconds=1.0,
        manifest_path=manifest_path,
        time_source=fake_time,
    )

    root._apply_batch(batch)
    root._apply_batch(batch)

    assert root.layout_state.tracker.import_asset_count == 1
    assert root.layout_state.tracker.import_dialog_filters[0]["label"] == "Sampler Assets"
    assert "manifest" in root.transport_controls.recovery_prompt
    autosave_dir = autosave_root / "demo"
    layout_files = [path for path in autosave_dir.iterdir() if path.name.endswith("layout.json")]
    assert layout_files, "Expected at least one autosave layout file"
    payload = json.loads(layout_files[0].read_text(encoding="utf-8"))
    assert "manifest_sha256" in payload


def test_tracker_mixer_root_import_project_bundle_updates_state(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    (bundle_root / "patterns").mkdir(parents=True)
    (bundle_root / "samples").mkdir(parents=True)
    pattern_path = bundle_root / "patterns" / "demo_pattern.json"
    pattern_path.write_text("{\n  \"steps\": []\n}", encoding="utf-8")
    asset_path = bundle_root / "samples" / "choir.wav"
    asset_path.write_bytes(b"demo audio asset")
    manifest_path = bundle_root / "project_manifest.json"
    manifest = {
        "manifest_version": "1.0.0",
        "project": {
            "id": "demo",
            "name": "Demo",
            "bpm": 120.0,
            "swing": 0.0,
            "created_at": "2025-11-28T00:00:00+00:00",
            "updated_at": "2025-11-28T00:00:00+00:00",
        },
        "patterns": [
            {
                "pattern_id": "demo_pattern",
                "path": "patterns/demo_pattern.json",
                "sha256": compute_file_sha256(pattern_path),
                "length_steps": 16,
                "step_count": 16,
            }
        ],
        "mixer_snapshots": [],
        "sampler_assets": [
            {
                "asset_name": "choir.wav",
                "relative_path": "samples/choir.wav",
                "sha256": compute_file_sha256(asset_path),
                "lufs_lu": -16.2,
                "source_uri": "s3://demo/choir.wav",
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    root = TrackerMixerRoot()
    destination = tmp_path / "restored"
    result = root.import_project_bundle(bundle_root, destination_root=destination)

    tracker_state = TrackerPanelState(pattern_id="demo_pattern")
    layout = TrackerMixerLayoutState(tracker=tracker_state, mixer=MixerPanelState())
    batch = PreviewBatchState(layout=layout, previews=[])
    root._apply_batch(batch)

    assert tracker_state.import_manifest_sha256 == result.manifest_sha256
    assert tracker_state.import_sampler_asset_names == ["choir.wav"]
    assert tracker_state.import_bundle_root is not None
    filters = tracker_state.import_dialog_filters
    assert filters and filters[0]["label"] == "Imported Assets"
    assert any(pattern.endswith(".wav") or pattern == "*" for pattern in filters[0]["patterns"])
    assert root.transport_controls.import_summary.startswith("Import")
    assert "Import" in root.transport_controls.recovery_prompt
    assert destination.exists()
