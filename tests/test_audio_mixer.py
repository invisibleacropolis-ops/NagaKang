import numpy as np

from audio.engine import BaseAudioModule, EngineConfig
from audio.mixer import MixerChannel, MixerGraph, MixerReturnBus, MixerSendConfig


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
