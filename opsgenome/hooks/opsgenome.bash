#!/usr/bin/env bash
# OpsGenome Shell Integration Hook (Bash)
# Captures terminal command execution and streams asynchronously to OpsGenome daemon.

_opsgenome_sock="${OPSGENOME_SOCKET_PATH:-$HOME/.opsgenome/daemon.sock}"
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

    # Redact in-process on client and transmit via secure Unix Domain Socket (never curl, never HTTP TCP)
    (
        python3 -m opsgenome.cli.client "$current_cmd" "$exit_code" "$duration" "$PWD" "$_opsgenome_sock" >/dev/null 2>&1 &
    )
}

PROMPT_COMMAND="_opsgenome_prompt_cmd; $PROMPT_COMMAND"
trap '_opsgenome_preexec' DEBUG
