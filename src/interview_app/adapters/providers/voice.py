"""Pinned LiveKit plugin construction for OpenRouter and ElevenLabs."""

from dataclasses import dataclass

from livekit.plugins import elevenlabs, openai

from interview_app.settings import Settings


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
            use_realtime=True,
            include_timestamps=True,
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
