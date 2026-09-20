"""OpenRouter implementation of the non-voice assessment boundary."""

from livekit.agents import APIConnectOptions, APIError, llm
from livekit.plugins import openai

from interview_app.application.ports.assessment import (
    PermanentAssessmentError,
    TransientAssessmentError,
)
from interview_app.domain.rubrics import StageRubric
from interview_app.domain.scoring import AssessmentTaskInput
from interview_app.resources.prompts import assessment_instructions
from interview_app.settings import Secret


class OpenRouterAssessmentModel:
    """Own one text-only LLM client; it has no STT, TTS, room, or session access."""

    def __init__(self, *, api_key: Secret, model: str) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("model must not be blank.")
        self._model_name = normalized_model
        self._llm = openai.LLM.with_openrouter(
            model=normalized_model,
            api_key=api_key.reveal(),
            app_name="Local Voice Interview Scoring",
            temperature=0.0,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def aclose(self) -> None:
        await self._llm.aclose()

    async def assess(self, task: AssessmentTaskInput, rubric: StageRubric) -> str:
        chat_context = llm.ChatContext()
        chat_context.add_message(
            role="system",
            content=assessment_instructions(task, rubric),
        )
        chunks: list[str] = []
        try:
            async with self._llm.chat(
                chat_ctx=chat_context,
                conn_options=APIConnectOptions(max_retry=0, timeout=60.0),
                response_format={"type": "json_object"},
            ) as stream:
                async for chunk in stream:
                    if chunk.delta is not None and chunk.delta.content is not None:
                        chunks.append(chunk.delta.content)
        except APIError as error:
            message = f"Assessment provider failed: {error.message}"
            if error.retryable:
                raise TransientAssessmentError(message) from error
            raise PermanentAssessmentError(message) from error
        output = "".join(chunks).strip()
        if not output:
            raise TransientAssessmentError("Assessment provider returned an empty response.")
        return output
