import numpy as np

from audio.effects import SoftKneeCompressorInsert, ThreeBandEqInsert
from audio.engine import BaseAudioModule, EngineConfig
from audio.mixer import (
    MixerChannel,
    MixerGraph,
    MixerReturnBus,
    MixerSendConfig,
    MixerSubgroup,
)


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
