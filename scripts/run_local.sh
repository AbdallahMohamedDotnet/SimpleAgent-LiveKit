#!/usr/bin/env bash
# Start the locally runnable interview stack from the repository root:
#   LiveKit dev server -> ROOM Agent Server -> config check -> retention cleanup
#   -> scoring worker -> results viewer -> operator console -> lifecycle probe.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/run_local.sh [options]

Starts the LiveKit dev server, scoring worker, results viewer and operator console, creates a
local room with the two sequential AgentSession stages, then keeps services running until Ctrl-C.

Options:
  --skip-cleanup     Do not run retention cleanup (deletes interviews older than 30 days).
  --no-probe         Do not create the room / start the two sessions.
  --dry-run NAME     Also run the provider-free two-stage lifecycle for candidate NAME.
  --no-agent         Do not start the ROOM Agent Server.
  --no-worker        Do not start the scoring worker.
  --no-results       Do not start the results viewer.
  --no-control       Do not start the operator console.
  --once             Run the room probe (and dry run), then stop everything and exit.
  -h, --help         Show this help.

Logs are written to data/logs/ (never candidate transcripts).
EOF
}

skip_cleanup=false
run_probe=true
run_agent=true
run_worker=true
run_results=true
run_control=true
exit_after_probe=false
dry_run_name=""

while (($#)); do
    case "$1" in
        --skip-cleanup) skip_cleanup=true ;;
        --no-probe) run_probe=false ;;
        --no-worker) run_worker=false ;;
        --no-results) run_results=false ;;
        --no-control) run_control=false ;;
        --once) exit_after_probe=true ;;
        --dry-run)
            shift
            if (($# == 0)) || [[ -z "$1" ]]; then
                echo "error: --dry-run requires a candidate name" >&2
                exit 2
            fi
            dry_run_name="$1"
            ;;
        --no-agent) run_agent=false ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$repo_root/.tools/uv-cache}"
uv_bin="$repo_root/.tools/bin/uv"
livekit_bin="$repo_root/.tools/bin/livekit-server"
[[ -x "$uv_bin" ]] || uv_bin="$(command -v uv || true)"
[[ -x "$livekit_bin" ]] || livekit_bin="$(command -v livekit-server || true)"

[[ -n "$uv_bin" ]] || { echo "error: uv not found (.tools/bin/uv or PATH)" >&2; exit 1; }
[[ -f .env ]] || { echo "error: .env missing; run: cp .env.example .env && chmod 600 .env" >&2; exit 1; }

log_dir="$repo_root/data/logs"
mkdir -p "$log_dir"

pids=()
names=()

log() { printf '[run_local] %s\n' "$*"; }

port_open() { (exec 3<>"/dev/tcp/$1/$2") 2>/dev/null; }

wait_for_port() {
    local host="$1" port="$2" label="$3" pid="${4:-}"
    for _ in $(seq 1 60); do
        port_open "$host" "$port" && return 0
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
            echo "error: $label exited during startup; see $log_dir" >&2
            return 1
        fi
        sleep 0.5
    done
    echo "error: $label did not open $host:$port within 30 seconds" >&2
    return 1
}

start_service() {
    local name="$1"
    shift
    "$@" >"$log_dir/$name.log" 2>&1 &
    pids+=("$!")
    names+=("$name")
    log "started $name (pid $!, log data/logs/$name.log)"
}

# Stop only processes this script started, newest first, so the worker can finish
# its current call before the LiveKit server goes away.
shutdown() {
    trap - EXIT INT TERM
    local index
    for ((index = ${#pids[@]} - 1; index >= 0; index--)); do
        if kill -0 "${pids[index]}" 2>/dev/null; then
            log "stopping ${names[index]}"
            kill -TERM "${pids[index]}" 2>/dev/null || true
        fi
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}
trap shutdown EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

interview() { "$uv_bin" run --frozen interview "$@"; }

log "syncing locked environment"
"$uv_bin" sync --frozen --group dev >/dev/null

log "validating configuration"
interview config-check

livekit_url="$(grep -E '^LIVEKIT_URL=' .env | tail -n1 | cut -d= -f2- || true)"
livekit_url="${LIVEKIT_URL:-${livekit_url:-ws://127.0.0.1:7880}}"
livekit_hostport="${livekit_url#*://}"
livekit_hostport="${livekit_hostport%%/*}"
livekit_host="${livekit_hostport%%:*}"
livekit_port="${livekit_hostport##*:}"
if [[ "$livekit_host" != "127.0.0.1" && "$livekit_host" != "localhost" ]]; then
    echo "error: LIVEKIT_URL must point at localhost for the --dev server (got $livekit_url)" >&2
    exit 1
fi

if port_open "$livekit_host" "$livekit_port"; then
    log "LiveKit already listening on $livekit_host:$livekit_port; reusing it"
else
    [[ -n "$livekit_bin" ]] || { echo "error: livekit-server not found" >&2; exit 1; }
    start_service livekit-server "$livekit_bin" --dev --bind 127.0.0.1
    wait_for_port "$livekit_host" "$livekit_port" "livekit-server" "${pids[-1]}"
fi

if [[ "$run_agent" == true ]]; then
    start_service agent-server "$uv_bin" run --frozen interview-agent dev --no-reload
    sleep 1
    if ! kill -0 "${pids[-1]}" 2>/dev/null; then
        echo "error: agent-server exited during startup; see $log_dir/agent-server.log" >&2
        exit 1
    fi
fi

if [[ "$skip_cleanup" == false ]]; then
    log "running retention cleanup"
    interview cleanup
fi

if [[ "$run_worker" == true ]]; then
    start_service scoring-worker "$uv_bin" run --frozen interview worker
fi

if [[ "$run_results" == true ]]; then
    results_port="$(grep -E '^RESULTS_PORT=' .env | tail -n1 | cut -d= -f2-)"
    results_port="${RESULTS_PORT:-${results_port:-8080}}"
    if port_open 127.0.0.1 "$results_port"; then
        echo "error: 127.0.0.1:$results_port is already in use; stop the other results viewer" >&2
        exit 1
    fi
    start_service results-viewer "$uv_bin" run --frozen interview results
    wait_for_port 127.0.0.1 "$results_port" "results-viewer" "${pids[-1]}"
    log "results viewer: http://127.0.0.1:$results_port/results"
fi

if [[ "$run_control" == true ]]; then
    control_port="$(grep -E '^CONTROL_PORT=' .env | tail -n1 | cut -d= -f2- || true)"
    control_port="${CONTROL_PORT:-${control_port:-8090}}"
    if port_open 127.0.0.1 "$control_port"; then
        echo "error: 127.0.0.1:$control_port is already in use; stop the other operator console" >&2
        exit 1
    fi
    start_service operator-console "$uv_bin" run --frozen interview control
    wait_for_port 127.0.0.1 "$control_port" "operator-console" "${pids[-1]}"
    log "operator console: http://127.0.0.1:$control_port/interviews/new"
fi

if [[ -n "$dry_run_name" ]]; then
    log "running provider-free two-stage dry run"
    interview dry-run --name "$dry_run_name"
fi

if [[ "$run_probe" == true ]]; then
    room="interview-local-$(date +%s)"
    log "creating room $room and running the HR -> technical AgentSession handoff"
    # The dev-server key pair is the fixed insecure pair documented in .env.example.
    livekit_key="${LIVEKIT_API_KEY:-$(grep -E '^LIVEKIT_API_KEY=' .env | tail -n1 | cut -d= -f2-)}"
    livekit_secret="${LIVEKIT_API_SECRET:-$(grep -E '^LIVEKIT_API_SECRET=' .env | tail -n1 | cut -d= -f2-)}"
    "$uv_bin" run --frozen python scripts/p03_livekit_handoff_probe.py \
        --url "$livekit_url" --api-key "$livekit_key" --api-secret "$livekit_secret" \
        --room "$room"
fi

if [[ "$exit_after_probe" == true ]]; then
    log "--once requested; shutting down"
    exit 0
fi

if ((${#pids[@]} == 0)); then
    log "nothing left running; exiting"
    exit 0
fi

log "services running; press Ctrl-C to stop"
# Exit as soon as any supervised service dies instead of leaving a half-running stack.
wait -n "${pids[@]}" || true
for index in "${!pids[@]}"; do
    if ! kill -0 "${pids[index]}" 2>/dev/null; then
        echo "error: ${names[index]} exited unexpectedly; see data/logs/${names[index]}.log" >&2
    fi
done
exit 1
