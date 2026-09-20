from interview_app.settings import ConfigurationError, Settings


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
