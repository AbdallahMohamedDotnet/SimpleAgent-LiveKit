import asyncio

from interview_app.adapters.providers import OpenRouterAssessmentModel, build_voice_providers
from interview_app.adapters.providers.voice import END_OF_TURN_SILENCE_SECONDS
from interview_app.settings import Secret, Settings


def test_pinned_provider_options_construct_without_network_access() -> None:
    async def exercise() -> None:
        settings = Settings.from_mapping(
            {
                "LIVEKIT_API_KEY": "local-key",
                "LIVEKIT_API_SECRET": "local-secret",
                "OPENROUTER_API_KEY": "not-used-for-a-request",
                "ELEVEN_API_KEY": "not-used-for-a-request",
                "HR_VOICE_ID": "hr-voice",
                "TECH_VOICE_ID": "technical-voice",
            }
        )
        providers = build_voice_providers(settings)
        assessor = OpenRouterAssessmentModel(
            api_key=Secret("not-used-for-a-request"),
            model=settings.openrouter_model,
        )
        assert providers.llm.model == "anthropic/claude-sonnet-5"
        assert providers.stt.model == "scribe_v2_realtime"
        # Server-side VAD is what commits final transcripts; without it turns never end.
        assert providers.stt._opts.server_vad == {
            "vad_silence_threshold_secs": END_OF_TURN_SILENCE_SECONDS
        }
        assert providers.hr_tts.model == "eleven_turbo_v2_5"
        assert providers.technical_tts.model == "eleven_turbo_v2_5"
        assert providers.hr_tts is not providers.technical_tts
        assert assessor.model_name == "anthropic/claude-sonnet-5"
        await asyncio.gather(
            assessor.aclose(),
            providers.llm.aclose(),
            providers.stt.aclose(),
            providers.hr_tts.aclose(),
            providers.technical_tts.aclose(),
        )

    asyncio.run(exercise())
