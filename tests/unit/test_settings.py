from interview_app.settings import (
    ConfigurationError,
    LaunchSettings,
    ResultsSettings,
    ScoringSettings,
    Settings,
)


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


def test_results_settings_describe_only_local_read_only_data() -> None:
    settings = ResultsSettings.from_mapping({})
    assert settings.sqlite_path.as_posix() == "data/interviews.sqlite3"
    assert settings.recordings_root.as_posix() == "data/recordings"
    assert not hasattr(settings, "host") and not hasattr(settings, "port")

    try:
        ResultsSettings.from_mapping({"RECORDINGS_DIR": "  "})
    except ConfigurationError as error:
        assert "must not be blank" in str(error)
    else:
        raise AssertionError("A blank recording root must be rejected.")


def test_launch_settings_keep_secrets_redacted_and_declare_no_http_surface() -> None:
    settings = LaunchSettings.from_mapping(valid_values())
    assert settings.agent_name == "interview-agent"
    assert settings.livekit_url == "ws://127.0.0.1:7880"
    assert "local-secret" not in repr(settings)
    assert not hasattr(settings, "host") and not hasattr(settings, "port")

    for values in (
        {**valid_values(), "LIVEKIT_API_SECRET": ""},
        {**valid_values(), "INTERVIEW_AGENT_NAME": " "},
    ):
        try:
            LaunchSettings.from_mapping(values)
        except ConfigurationError:
            pass
        else:
            raise AssertionError("Incomplete launch settings were accepted.")
