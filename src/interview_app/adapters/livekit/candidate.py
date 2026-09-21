"""Terminal microphone/speaker participant for a local LiveKit interview room."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from livekit import api, rtc

from interview_app.settings import Secret


class CandidateAudioUnavailableError(RuntimeError):
    """Raised when local PortAudio devices cannot support the terminal participant."""


@dataclass(frozen=True, slots=True)
class CandidateConnection:
    url: str
    api_key: Secret
    api_secret: Secret
    room_name: str
    identity: str
    input_device: str | int | None = None
    output_device: str | int | None = None


class SoundDeviceBackend:
    """Validate and own the optional PortAudio-backed device streams."""

    def __init__(self, module: ModuleType | None = None) -> None:
        self._module = module or self._load_module()

    @staticmethod
    def _load_module() -> ModuleType:
        try:
            return importlib.import_module("sounddevice")
        except (ImportError, OSError) as error:
            raise CandidateAudioUnavailableError(
                "PortAudio is unavailable. Install the host PortAudio library and expose a "
                "microphone and speaker, then rerun 'interview devices'."
            ) from error

    def devices(self) -> str:
        try:
            return str(self._module.query_devices())
        except Exception as error:
            raise CandidateAudioUnavailableError(
                "Audio devices could not be enumerated."
            ) from error

    def open_input(
        self,
        callback: Callable[[bytes], None],
        *,
        device: str | int | None,
        sample_rate: int,
        channels: int,
        blocksize: int,
    ) -> Any:
        def on_audio(
            data: Any,
            _frames: int,
            _time_info: Any,
            status: Any,
        ) -> None:
            if status:
                return
            callback(bytes(data))

        try:
            return self._module.RawInputStream(
                samplerate=sample_rate,
                blocksize=blocksize,
                device=device,
                channels=channels,
                dtype="int16",
                callback=on_audio,
            )
        except Exception as error:
            raise CandidateAudioUnavailableError(
                "The selected microphone could not be opened."
            ) from error

    def open_output(
        self,
        *,
        device: str | int | None,
        sample_rate: int,
        channels: int,
    ) -> Any:
        try:
            return self._module.RawOutputStream(
                samplerate=sample_rate,
                device=device,
                channels=channels,
                dtype="int16",
            )
        except Exception as error:
            raise CandidateAudioUnavailableError(
                "The selected speaker could not be opened."
            ) from error


class TerminalCandidateClient:
    """Publish microphone PCM and play subscribed agent audio until disconnected."""

    SAMPLE_RATE = 48_000
    CHANNELS = 1
    BLOCKSIZE = 480

    def __init__(
        self,
        connection: CandidateConnection,
        *,
        audio: SoundDeviceBackend | None = None,
    ) -> None:
        self._connection = connection
        self._audio = audio or SoundDeviceBackend()
        self._input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._playback_tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        room = rtc.Room()
        loop = asyncio.get_running_loop()
        disconnected = asyncio.Event()
        room.on("disconnected", lambda *_: disconnected.set())
        room.on("track_subscribed", self._on_track_subscribed)
        token = (
            api.AccessToken(
                self._connection.api_key.reveal(),
                self._connection.api_secret.reveal(),
            )
            .with_identity(self._connection.identity)
            .with_grants(api.VideoGrants(room_join=True, room=self._connection.room_name))
            .to_jwt()
        )
        source = rtc.AudioSource(self.SAMPLE_RATE, self.CHANNELS)
        microphone_track = rtc.LocalAudioTrack.create_audio_track("microphone", source)

        def enqueue_from_audio_thread(chunk: bytes) -> None:
            loop.call_soon_threadsafe(self._queue_microphone_chunk, chunk)

        input_stream = self._audio.open_input(
            enqueue_from_audio_thread,
            device=self._connection.input_device,
            sample_rate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            blocksize=self.BLOCKSIZE,
        )
        capture_task: asyncio.Task[None] | None = None
        try:
            await room.connect(self._connection.url, token)
            options = rtc.TrackPublishOptions()
            options.source = rtc.TrackSource.SOURCE_MICROPHONE
            await room.local_participant.publish_track(microphone_track, options)
            input_stream.start()
            capture_task = asyncio.create_task(self._publish_microphone(source))
            await disconnected.wait()
        except asyncio.CancelledError:
            raise
        finally:
            input_stream.stop()
            input_stream.close()
            if capture_task is not None:
                capture_task.cancel()
                await asyncio.gather(capture_task, return_exceptions=True)
            for task in tuple(self._playback_tasks):
                task.cancel()
            if self._playback_tasks:
                await asyncio.gather(*self._playback_tasks, return_exceptions=True)
            await source.aclose()
            if room.isconnected():
                await room.disconnect()

    def _queue_microphone_chunk(self, chunk: bytes) -> None:
        if self._input_queue.full():
            _ = self._input_queue.get_nowait()
        self._input_queue.put_nowait(chunk)

    async def _publish_microphone(self, source: rtc.AudioSource) -> None:
        while True:
            chunk = await self._input_queue.get()
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=self.SAMPLE_RATE,
                num_channels=self.CHANNELS,
                samples_per_channel=len(chunk) // 2,
            )
            await source.capture_frame(frame)

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        _participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        task = asyncio.create_task(self._play_track(track))
        self._playback_tasks.add(task)
        task.add_done_callback(self._playback_tasks.discard)

    async def _play_track(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream(
            track,
            sample_rate=self.SAMPLE_RATE,
            num_channels=self.CHANNELS,
            capacity=100,
        )
        output = self._audio.open_output(
            device=self._connection.output_device,
            sample_rate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
        )
        try:
            output.start()
            async for event in stream:
                await asyncio.to_thread(output.write, bytes(event.frame.data))
        finally:
            output.stop()
            output.close()
            await stream.aclose()
