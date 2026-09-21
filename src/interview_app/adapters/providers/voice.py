"""Pinned LiveKit plugin construction for OpenRouter and ElevenLabs."""

from dataclasses import dataclass
from typing import Final

from livekit.plugins import elevenlabs, openai

from interview_app.settings import Settings

# Scribe realtime only emits a final transcript when a commit happens. Neither AgentSession runs a
# local VAD that would send a manual commit, so ElevenLabs' server-side VAD must commit instead;
# without it the sessions receive partial transcripts only and a candidate's turn never ends.
# Two seconds is deliberately longer than the provider's 1.5-second default so ordinary
# mid-answer hesitation is not taken as a finished answer (P04). Longer, explicit thinking time
# is governed separately by the thinking-hold policy.
END_OF_TURN_SILENCE_SECONDS: Final = 2.0


@dataclass(frozen=True, slots=True)
class VoiceProviderBundle:
    llm: openai.LLM
    stt: elevenlabs.STT
    hr_tts: elevenlabs.TTS
    technical_tts: elevenlabs.TTS


def build_voice_providers(settings: Settings) -> VoiceProviderBundle:
    """Map validated settings only to options supported by pinned SDK 1.8.2."""
    return VoiceProviderBundle(
        llm=openai.LLM.with_openrouter(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key.reveal(),
            app_name="Local Voice Interview",
        ),
        stt=elevenlabs.STT(
            api_key=settings.eleven_api_key.reveal(),
            model=settings.eleven_stt_model,
            language_code=settings.interview_language,
            include_timestamps=True,
            server_vad={"vad_silence_threshold_secs": END_OF_TURN_SILENCE_SECONDS},
        ),
        hr_tts=elevenlabs.TTS(
            api_key=settings.eleven_api_key.reveal(),
            model=settings.eleven_tts_model,
            voice_id=settings.hr_voice_id,
            language=settings.interview_language,
        ),
        technical_tts=elevenlabs.TTS(
            api_key=settings.eleven_api_key.reveal(),
            model=settings.eleven_tts_model,
            voice_id=settings.tech_voice_id,
            language=settings.interview_language,
        ),
    )
