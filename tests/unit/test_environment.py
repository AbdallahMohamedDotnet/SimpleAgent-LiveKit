from pathlib import Path

import pytest

from interview_app.entrypoints.environment import load_environment
from interview_app.settings import ConfigurationError


def test_env_file_is_loaded_and_process_environment_takes_precedence(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local settings\nOPENROUTER_API_KEY=file-secret\nRESULTS_PORT='8080'\n",
        encoding="utf-8",
    )

    values = load_environment(
        env_file=env_file,
        process_environment={"OPENROUTER_API_KEY": "process-secret"},
    )

    assert values["OPENROUTER_API_KEY"] == "process-secret"
    assert values["RESULTS_PORT"] == "8080"


@pytest.mark.parametrize(
    "entry",
    ["NOT_AN_ASSIGNMENT", "1INVALID=value", "VALUE='unclosed"],
)
def test_invalid_env_entries_fail_with_location(tmp_path: Path, entry: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(entry, encoding="utf-8")

    with pytest.raises(ConfigurationError, match=r"\.env:1"):
        load_environment(env_file=env_file, process_environment={})
