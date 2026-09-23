from typing import cast

from livekit import rtc

from interview_app.adapters.livekit.candidate import WebRtcEchoCanceller


class FakeAudioProcessingModule:
    def __init__(self) -> None:
        self.delays: list[int] = []
        self.microphone_frames: list[rtc.AudioFrame] = []
        self.speaker_frames: list[rtc.AudioFrame] = []

    def set_stream_delay_ms(self, delay_ms: int) -> None:
        self.delays.append(delay_ms)

    def process_stream(self, frame: rtc.AudioFrame) -> None:
        self.microphone_frames.append(frame)

    def process_reverse_stream(self, frame: rtc.AudioFrame) -> None:
        self.speaker_frames.append(frame)


def _ten_millisecond_frame() -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=bytes(480 * 2),
        sample_rate=48_000,
        num_channels=1,
        samples_per_channel=480,
    )


def test_echo_canceller_receives_speaker_reference_and_microphone_audio() -> None:
    module = FakeAudioProcessingModule()
    processor = WebRtcEchoCanceller(cast(rtc.AudioProcessingModule, module))
    speaker = _ten_millisecond_frame()
    microphone = _ten_millisecond_frame()

    processor.process_speaker(speaker)
    processor.process_microphone(microphone)

    assert module.delays == [0]
    assert module.speaker_frames == [speaker]
    assert module.microphone_frames == [microphone]
