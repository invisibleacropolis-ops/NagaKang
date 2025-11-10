import numpy as np
import pytest

from audio.effects import (
    PlateReverbInsert,
    SoftKneeCompressorInsert,
    StereoFeedbackDelayInsert,
    ThreeBandEqInsert,
)
from audio.engine import BaseAudioModule, EngineConfig, TempoMap
from audio.mixer import (
    MeterReading,
    MixerChannel,
    MixerGraph,
    MixerReturnBus,
    MixerSendConfig,
    MixerSubgroup,
)
from audio.tracker_bridge import PatternPerformanceBridge
from domain.models import AutomationPoint, InstrumentDefinition, InstrumentModule, Pattern, PatternStep


class ConstantModule(BaseAudioModule):
    def __init__(self, name: str, config: EngineConfig, value: float) -> None:
        super().__init__(name, config, [])
        self._value = value

    def process(self, frames: int) -> np.ndarray:  # pragma: no cover - exercised via mixer
        return np.full((frames, self.config.channels), self._value, dtype=np.float32)


def test_channel_pan_and_fader_controls() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)
    source = ConstantModule("const", config, value=0.5)
    channel = MixerChannel("track", source=source, config=config)

    channel.set_fader_db(-6.0)
    channel.set_pan(-1.0)

    main, sends = channel.process(4)
    assert sends == {}
    np.testing.assert_allclose(main[:, 0], np.full(4, 0.5 * 10 ** (-6 / 20), dtype=np.float32))
    np.testing.assert_allclose(main[:, 1], np.zeros(4, dtype=np.float32))


def test_send_routes_audio_to_return_bus() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=4, channels=2)
    source = ConstantModule("const", config, value=0.25)

    def double_gain(buffer: np.ndarray) -> np.ndarray:
        return buffer * 2.0

    channel = MixerChannel(
        "track",
        source=source,
        config=config,
        sends=[MixerSendConfig(bus="fx", level_db=-3.0, pre_fader=True)],
    )
    mixer = MixerGraph(config)
    mixer.add_channel(channel)
    mixer.add_return_bus(MixerReturnBus("fx", processor=double_gain))

    block = mixer.process_block(4)

    direct_expected = np.full((4, 2), 0.25, dtype=np.float32)
    send_level = 0.25 * 10 ** (-3 / 20)
    return_expected = np.full((4, 2), send_level * 2.0, dtype=np.float32)
    np.testing.assert_allclose(block, direct_expected + return_expected)


def test_feedback_delay_tail_persists_across_blocks() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=64, channels=2)
    delay = StereoFeedbackDelayInsert(
        config,
        delay_ms=1.0,
        feedback=0.4,
        mix=1.0,
    )
    impulse = np.zeros((64, 2), dtype=np.float32)
    impulse[0, :] = 1.0
    first = delay(impulse)
    second = delay(np.zeros_like(impulse))
    delay_samples = int(round(1.0 * config.sample_rate / 1_000.0))
    assert np.any(np.abs(first[delay_samples:]) > 0.0)
    assert np.any(np.abs(second) > 0.0)


def test_plate_reverb_emits_continuing_tail() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=64, channels=2)
    reverb = PlateReverbInsert(
        config,
        pre_delay_ms=0.0,
        mix=1.0,
        decay=0.6,
    )
    impulse = np.zeros((64, 2), dtype=np.float32)
    impulse[0, :] = 1.0
    first = reverb(impulse)
    second = reverb(np.zeros_like(impulse))
    tail = reverb(np.zeros((2048, 2), dtype=np.float32))
    combined = np.vstack([first, second, tail])
    assert np.any(np.abs(combined) > 0.0)
    assert np.any(np.abs(tail[-256:]) > 0.0)


def test_three_band_eq_enhances_highs() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=64, channels=2)
    eq = ThreeBandEqInsert(config, high_gain_db=6.0, high_freq=5_000.0)
    t = np.arange(128, dtype=np.float32) / config.sample_rate
    tone = np.sin(2.0 * np.pi * 5_000.0 * t).astype(np.float32) * 0.1
    buffer = np.repeat(tone[:, None], config.channels, axis=1)
    processed = eq(buffer)
    assert processed.std() > buffer.std()


def test_soft_knee_compressor_reduces_dynamic_range() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    compressor = SoftKneeCompressorInsert(
        config,
        threshold_db=-24.0,
        ratio=6.0,
        attack_ms=5.0,
        release_ms=80.0,
        makeup_gain_db=0.0,
    )
    ramp = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    buffer = np.repeat(ramp[:, None], config.channels, axis=1)
    processed = compressor(buffer)
    assert processed.ptp() < buffer.ptp()


def test_channel_insert_reordering() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)

    def add_one(buffer: np.ndarray) -> np.ndarray:
        return buffer + 1.0

    def double(buffer: np.ndarray) -> np.ndarray:
        return buffer * 2.0

    source = ConstantModule("const", config, value=1.0)
    channel = MixerChannel(
        "track",
        source=source,
        config=config,
        inserts=[add_one, double],
    )

    main, _ = channel.process(2)
    np.testing.assert_allclose(main, np.full((2, 2), 4.0, dtype=np.float32))

    channel.move_insert(0, 1)
    main, _ = channel.process(2)
    np.testing.assert_allclose(main, np.full((2, 2), 3.0, dtype=np.float32))


def test_subgroup_routing_and_solo_logic() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)
    channel_a = MixerChannel(
        "a",
        source=ConstantModule("const_a", config, value=0.5),
        config=config,
        solo=False,
    )
    channel_b = MixerChannel(
        "b",
        source=ConstantModule("const_b", config, value=0.25),
        config=config,
    )
    subgroup = MixerSubgroup("band", config=config, fader_db=-6.0)
    mixer = MixerGraph(config)
    mixer.add_channel(channel_a)
    mixer.add_channel(channel_b)
    mixer.add_subgroup(subgroup)
    mixer.assign_channel_to_group("a", "band")
    mixer.assign_channel_to_group("b", "band")

    block = mixer.process_block(4)
    expected = (0.5 + 0.25) * 10 ** (-6 / 20)
    np.testing.assert_allclose(block, np.full((4, 2), expected, dtype=np.float32))

    channel_a.set_solo(True)
    block = mixer.process_block(4)
    expected = 0.5 * 10 ** (-6 / 20)
    np.testing.assert_allclose(block, np.full((4, 2), expected, dtype=np.float32))

    channel_a.set_solo(False)
    subgroup.set_solo(True)
    block = mixer.process_block(4)
    expected = (0.5 + 0.25) * 10 ** (-6 / 20)
    np.testing.assert_allclose(block, np.full((4, 2), expected, dtype=np.float32))


def test_nested_subgroup_routing_and_metering() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)
    drums = MixerSubgroup("drums", config=config, fader_db=-6.0)
    band = MixerSubgroup("band", config=config, fader_db=0.0)
    mixer = MixerGraph(config)
    mixer.add_subgroup(drums)
    mixer.add_subgroup(band)
    mixer.assign_subgroup_to_group("drums", "band")

    kick = MixerChannel(
        "kick",
        source=ConstantModule("kick_src", config, value=0.5),
        config=config,
    )
    snare = MixerChannel(
        "snare",
        source=ConstantModule("snare_src", config, value=0.25),
        config=config,
    )
    mixer.add_channel(kick)
    mixer.add_channel(snare)
    mixer.assign_channel_to_group("kick", "drums")
    mixer.assign_channel_to_group("snare", "drums")

    block = mixer.process_block(4)
    expected_linear = (0.5 + 0.25) * 10 ** (-6 / 20)
    np.testing.assert_allclose(block, np.full((4, 2), expected_linear, dtype=np.float32))

    meters = mixer.subgroup_meters
    assert set(meters) == {"drums", "band"}
    expected_peak_db = float(20.0 * np.log10(expected_linear))
    assert isinstance(meters["drums"], MeterReading)
    assert meters["drums"].peak_db == pytest.approx(expected_peak_db, abs=0.5)
    assert meters["band"].peak_db == pytest.approx(expected_peak_db, abs=0.5)


def test_mixer_automation_updates_send_subgroup_and_return() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)
    channel = MixerChannel(
        "track",
        source=ConstantModule("src", config, value=0.5),
        config=config,
        sends=[MixerSendConfig(bus="fx", level_db=-60.0)],
    )
    subgroup = MixerSubgroup("band", config=config)
    graph = MixerGraph(config)
    graph.add_channel(channel)
    graph.add_subgroup(subgroup)
    graph.assign_channel_to_group("track", "band")
    graph.add_return_bus(MixerReturnBus("fx"))

    block_duration = config.block_size / config.sample_rate
    graph.schedule_parameter_change(
        "mixer:channel:track",
        "send:fx",
        value=-12.0,
        time_seconds=0.0,
        source="test",
    )
    graph.schedule_parameter_change(
        "mixer:subgroup:band",
        "fader_db",
        value=-6.0,
        time_seconds=block_duration,
        source="test",
    )
    graph.schedule_parameter_change(
        "mixer:return:fx",
        "level_db",
        value=-3.0,
        time_seconds=0.0,
        source="test",
    )

    graph.process_block(config.block_size)
    assert channel.get_send_level_db("fx") == pytest.approx(-12.0)
    assert subgroup.fader_db == pytest.approx(0.0)
    assert graph.returns["fx"].level_db == pytest.approx(-3.0)
    assert isinstance(graph.master_meter, MeterReading)
    assert graph.master_meter.peak_db > -120.0

    graph.process_block(config.block_size)
    assert subgroup.fader_db == pytest.approx(-6.0)


def test_pattern_bridge_schedules_mixer_automation() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=8, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)
    mixer = MixerGraph(config)
    subgroup = MixerSubgroup("band", config=config)
    mixer.add_subgroup(subgroup)
    mixer.add_return_bus(MixerReturnBus("plate"))
    channel = MixerChannel(
        "Lead",
        source=ConstantModule("lead_src", config, value=0.4),
        config=config,
        sends=[MixerSendConfig(bus="plate", level_db=-24.0)],
    )
    mixer.add_channel(channel)
    mixer.assign_channel_to_group("Lead", "band")

    pattern = Pattern(
        id="pat",
        name="Pat",
        length_steps=4,
        steps=[PatternStep(note=60, instrument_id="inst")],
        automation={
            "mixer:channel:Lead.send:plate|range=-24:-6": [
                AutomationPoint(position_beats=0.0, value=1.0)
            ],
            "mixer:subgroup:band.fader_db|range=-12:0": [
                AutomationPoint(position_beats=0.0, value=0.5)
            ],
            "mixer:return:plate.level_db|range=-18:-6": [
                AutomationPoint(position_beats=0.0, value=1.0)
            ],
        },
    )
    instrument = InstrumentDefinition(
        id="inst",
        name="Instrument",
        modules=[InstrumentModule(id="osc", type="sine")],
        macros={"mixer_channel": ["Lead"]},
    )

    bridge = PatternPerformanceBridge(config, tempo, mixer=mixer)
    bridge.render_pattern(pattern, instrument)

    assert any(
        event.module == "mixer:channel:Lead" and event.parameter == "send:plate"
        for event in mixer.automation_events
    )
    assert any(
        event.module == "mixer:subgroup:band" and event.parameter == "fader_db"
        for event in mixer.automation_events
    )
    assert any(
        event.module == "mixer:return:plate" and event.parameter == "level_db"
        for event in mixer.automation_events
    )

    mixer.process_block(config.block_size)
    assert channel.get_send_level_db("plate") == pytest.approx(-6.0)
    assert subgroup.fader_db == pytest.approx(-6.0)
    assert mixer.returns["plate"].level_db == pytest.approx(-6.0)


def test_pattern_bridge_renders_audio_through_mixer_channel() -> None:
    config = EngineConfig(sample_rate=48_000, block_size=16, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)
    mixer = MixerGraph(config)
    channel = MixerChannel(
        "Lead",
        source=ConstantModule("silence", config, value=0.0),
        config=config,
    )
    mixer.add_channel(channel)

    pattern = Pattern(
        id="pat",
        name="Pat",
        length_steps=4,
        steps=[PatternStep(note=60, instrument_id="inst")],
    )
    instrument = InstrumentDefinition(
        id="inst",
        name="Instrument",
        modules=[InstrumentModule(id="osc", type="sine")],
        macros={"mixer_channel": ["Lead"]},
    )

    bridge = PatternPerformanceBridge(config, tempo, mixer=mixer)
    playback = bridge.render_pattern(pattern, instrument)

    assert np.any(np.abs(playback.buffer) > 0.0)
    restored_source = mixer.channels["Lead"].source
    assert isinstance(restored_source, ConstantModule)
    assert playback.mixer_snapshot is not None
    assert "Lead" not in playback.mixer_snapshot.subgroup_meters  # channel bypasses subgroup
    assert playback.mixer_snapshot.master_meter.peak_db <= 0.0
