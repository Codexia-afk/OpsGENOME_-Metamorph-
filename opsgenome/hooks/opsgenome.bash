#!/usr/bin/env bash
# OpsGenome Shell Integration Hook (Bash)
# Captures terminal command execution and streams asynchronously to OpsGenome daemon.

_opsgenome_daemon_url="${OPSGENOME_DAEMON_URL:-http://127.0.0.1:8765/api/v1/events/capture}"
_opsgenome_last_cmd=""
_opsgenome_start_time=0

_opsgenome_preexec() {
    _opsgenome_last_cmd="$BASH_COMMAND"
    _opsgenome_start_time=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
}

_opsgenome_prompt_cmd() {
    local exit_code=$?
    if [ -z "$_opsgenome_last_cmd" ]; then
        return
    fi

    local end_time
    end_time=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
    local duration=$(( end_time - _opsgenome_start_time ))
    if [ "$duration" -lt 0 ]; then duration=0; fi

    local current_cmd="$_opsgenome_last_cmd"
    _opsgenome_last_cmd=""

    (
        curl -s -m 0.5 -X POST "$_opsgenome_daemon_url" \
            -H "Content-Type: application/json" \
            -d "{\"command\": $(echo "$current_cmd" | python3 -c 'import sys, json; print(json.dumps(sys.stdin.read().strip()))'), \"exit_code\": $exit_code, \"duration_ms\": $duration, \"cwd\": $(echo "$PWD" | python3 -c 'import sys, json; print(json.dumps(sys.stdin.read().strip()))')}" \
            >/dev/null 2>&1 &
    )
}

PROMPT_COMMAND="_opsgenome_prompt_cmd; $PROMPT_COMMAND"
trap '_opsgenome_preexec' DEBUG
