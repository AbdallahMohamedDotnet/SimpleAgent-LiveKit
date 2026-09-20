"""Single validated boundary for live runtime configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class Secret:
    _value: str

    def reveal(self) -> str:
        """Return the secret only at the infrastructure construction boundary."""
        return self._value

    def __repr__(self) -> str:
        return "Secret('********')"

    def __str__(self) -> str:
        return "********"


@dataclass(frozen=True, slots=True)
class Settings:
    livekit_url: str
    livekit_api_key: Secret
    livekit_api_secret: Secret
    openrouter_api_key: Secret
    openrouter_model: str
    eleven_api_key: Secret
    eleven_stt_model: str
    eleven_tts_model: str
    hr_voice_id: str
    tech_voice_id: str
    interview_language: str
    hr_target_seconds: int
    tech_target_seconds: int
    idle_checkin_seconds: int
    thinking_hold_seconds: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Settings:
        required = (
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "OPENROUTER_API_KEY",
            "ELEVEN_API_KEY",
            "HR_VOICE_ID",
            "TECH_VOICE_ID",
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise ConfigurationError("Missing required settings: " + ", ".join(sorted(missing)))

        hr_voice_id = values["HR_VOICE_ID"].strip()
        tech_voice_id = values["TECH_VOICE_ID"].strip()
        if hr_voice_id == tech_voice_id:
            raise ConfigurationError("HR_VOICE_ID and TECH_VOICE_ID must be distinct.")

        fixed_numbers = {
            "HR_TARGET_SECONDS": 300,
            "TECH_TARGET_SECONDS": 300,
            "IDLE_CHECKIN_SECONDS": 5,
            "THINKING_HOLD_SECONDS": 20,
        }
        parsed_numbers: dict[str, int] = {}
        for name, expected in fixed_numbers.items():
            raw_value = values.get(name, str(expected)).strip()
            try:
                parsed = int(raw_value)
            except ValueError as error:
                raise ConfigurationError(f"{name} must be an integer.") from error
            if parsed != expected:
                raise ConfigurationError(f"{name} is fixed at {expected}.")
            parsed_numbers[name] = parsed
        language = values.get("INTERVIEW_LANGUAGE", "en").strip().lower()
        if language != "en":
            raise ConfigurationError("INTERVIEW_LANGUAGE is fixed at en.")

        return cls(
            livekit_url=values.get("LIVEKIT_URL", "ws://127.0.0.1:7880").strip(),
            livekit_api_key=Secret(values["LIVEKIT_API_KEY"].strip()),
            livekit_api_secret=Secret(values["LIVEKIT_API_SECRET"].strip()),
            openrouter_api_key=Secret(values["OPENROUTER_API_KEY"].strip()),
            openrouter_model=values.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-5").strip(),
            eleven_api_key=Secret(values["ELEVEN_API_KEY"].strip()),
            eleven_stt_model=values.get("ELEVEN_STT_MODEL", "scribe_v2_realtime").strip(),
            eleven_tts_model=values.get("ELEVEN_TTS_MODEL", "eleven_turbo_v2_5").strip(),
            hr_voice_id=hr_voice_id,
            tech_voice_id=tech_voice_id,
            interview_language=language,
            hr_target_seconds=parsed_numbers["HR_TARGET_SECONDS"],
            tech_target_seconds=parsed_numbers["TECH_TARGET_SECONDS"],
            idle_checkin_seconds=parsed_numbers["IDLE_CHECKIN_SECONDS"],
            thinking_hold_seconds=parsed_numbers["THINKING_HOLD_SECONDS"],
        )


@dataclass(frozen=True, slots=True)
class ScoringSettings:
    sqlite_path: Path
    openrouter_api_key: Secret
    openrouter_model: str
    worker_id: str
    poll_interval_seconds: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ScoringSettings:
        api_key = values.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise ConfigurationError("Missing required setting: OPENROUTER_API_KEY")
        model = values.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-5").strip()
        worker_id = values.get("SCORING_WORKER_ID", "local-scoring-worker").strip()
        sqlite_path = values.get("SQLITE_PATH", "data/interviews.sqlite3").strip()
        if not model or not worker_id or not sqlite_path:
            raise ConfigurationError(
                "OPENROUTER_MODEL, SCORING_WORKER_ID, and SQLITE_PATH must not be blank."
            )
        raw_poll = values.get("SCORING_POLL_SECONDS", "2").strip()
        try:
            poll_interval = float(raw_poll)
        except ValueError as error:
            raise ConfigurationError("SCORING_POLL_SECONDS must be numeric.") from error
        if poll_interval <= 0:
            raise ConfigurationError("SCORING_POLL_SECONDS must be positive.")
        return cls(
            sqlite_path=Path(sqlite_path),
            openrouter_api_key=Secret(api_key),
            openrouter_model=model,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval,
        )
