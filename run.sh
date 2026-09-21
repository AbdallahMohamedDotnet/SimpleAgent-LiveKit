#!/usr/bin/env bash
# Open the interactive operator menu with the environment this checkout needs.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.tools/uv-cache}"

# Project-local PortAudio runtime, so microphone/speaker selection works without a system package.
portaudio_lib="$PWD/.tools/portaudio/usr/lib/x86_64-linux-gnu"
if [[ -d "$portaudio_lib" ]]; then
    export LD_LIBRARY_PATH="$portaudio_lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

uv_bin="$PWD/.tools/bin/uv"
[[ -x "$uv_bin" ]] || uv_bin="$(command -v uv || true)"
[[ -n "$uv_bin" ]] || { echo "error: uv not found (.tools/bin/uv or PATH)" >&2; exit 1; }

if [[ ! -f .env ]]; then
    echo "error: .env missing; run: cp .env.example .env && chmod 600 .env" >&2
    exit 1
fi

"$uv_bin" sync --frozen --group dev >/dev/null
exec "$uv_bin" run --frozen python main.py "$@"
