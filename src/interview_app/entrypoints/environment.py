"""Load operator configuration at the process boundary."""

import os
from collections.abc import Mapping
from pathlib import Path

from interview_app.settings import ConfigurationError


def load_environment(
    *,
    env_file: Path = Path(".env"),
    process_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return .env values overlaid by the real process environment.

    The loader intentionally supports the simple ``KEY=VALUE`` format used by
    this project. Shell execution, interpolation, and multiline values are not
    supported, so untrusted content can never become instructions.
    """
    values: dict[str, str] = {}
    if env_file.exists():
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise ConfigurationError(f"Unable to read environment file: {env_file}") from error
        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ConfigurationError(f"Invalid environment entry at {env_file}:{line_number}.")
            name, raw_value = line.split("=", 1)
            name = name.strip()
            if not name or not name.replace("_", "A").isalnum() or name[0].isdigit():
                raise ConfigurationError(f"Invalid environment name at {env_file}:{line_number}.")
            values[name] = _unquote(raw_value.strip(), env_file, line_number)

    values.update(process_environment if process_environment is not None else os.environ)
    return values


def _unquote(value: str, env_file: Path, line_number: int) -> str:
    if not value or value[0] not in {"'", '"'}:
        return value
    if len(value) < 2 or value[-1] != value[0]:
        raise ConfigurationError(f"Unclosed quote at {env_file}:{line_number}.")
    return value[1:-1]
