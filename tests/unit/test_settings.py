from interview_app.settings import ConfigurationError, ResultsSettings, ScoringSettings, Settings


def valid_values() -> dict[str, str]:
    return {
        "LIVEKIT_API_KEY": "local-key",
        "LIVEKIT_API_SECRET": "local-secret",
        "OPENROUTER_API_KEY": "openrouter-secret",
        "ELEVEN_API_KEY": "eleven-secret",
        "HR_VOICE_ID": "hr-voice",
        "TECH_VOICE_ID": "tech-voice",
    }


def test_missing_settings_are_named_without_exposing_present_secrets() -> None:
    values = valid_values()
    secret = values.pop("OPENROUTER_API_KEY")

    try:
        Settings.from_mapping(values)
    except ConfigurationError as error:
        message = str(error)
    else:
        raise AssertionError("Expected missing configuration to fail.")

    assert "OPENROUTER_API_KEY" in message
    assert secret not in message
    assert "local-secret" not in message


def test_voice_ids_must_be_distinct() -> None:
    values = valid_values()
    values["TECH_VOICE_ID"] = values["HR_VOICE_ID"]

    try:
        Settings.from_mapping(values)
    except ConfigurationError as error:
        assert "must be distinct" in str(error)
    else:
        raise AssertionError("Expected identical voice IDs to fail.")


def test_secret_repr_is_redacted() -> None:
    settings = Settings.from_mapping(valid_values())

    assert "openrouter-secret" not in repr(settings)
    assert str(settings.openrouter_api_key) == "********"


def test_fixed_language_and_timing_cannot_be_silently_changed() -> None:
    values = valid_values()
    values["HR_TARGET_SECONDS"] = "240"
    try:
        Settings.from_mapping(values)
    except ConfigurationError as error:
        assert "fixed at 300" in str(error)
    else:
        raise AssertionError("The fixed interview duration must be enforced.")


def test_scoring_worker_settings_require_only_its_owned_provider_and_store() -> None:
    settings = ScoringSettings.from_mapping(
        {
            "OPENROUTER_API_KEY": "worker-secret",
            "SQLITE_PATH": "data/test.sqlite3",
            "SCORING_POLL_SECONDS": "0.5",
        }
    )

    assert settings.sqlite_path.as_posix() == "data/test.sqlite3"
    assert settings.openrouter_model == "anthropic/claude-sonnet-5"
    assert settings.poll_interval_seconds == 0.5
    assert "worker-secret" not in repr(settings)


def test_results_settings_are_localhost_only() -> None:
    settings = ResultsSettings.from_mapping({})
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080

    try:
        ResultsSettings.from_mapping({"RESULTS_HOST": "0.0.0.0"})
    except ConfigurationError as error:
        assert "fixed at 127.0.0.1" in str(error)
    else:
        raise AssertionError("The results viewer must remain localhost-only.")

    try:
        ResultsSettings.from_mapping({"RESULTS_PORT": "70000"})
    except ConfigurationError as error:
        assert "between 0 and 65535" in str(error)
    else:
        raise AssertionError("An invalid results port must be rejected.")
