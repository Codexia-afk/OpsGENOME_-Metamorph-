#!/usr/bin/env zsh
# OpsGenome Shell Integration Hook (Zsh)
# Captures terminal command execution, exit codes, and durations, streaming them to local OpsGenome daemon.

_opsgenome_sock="${OPSGENOME_SOCKET_PATH:-$HOME/.opsgenome/daemon.sock}"
_opsgenome_last_cmd=""
_opsgenome_start_time=0

_opsgenome_preexec() {
    _opsgenome_last_cmd="$1"
    _opsgenome_start_time=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
}

_opsgenome_precmd() {
    local exit_code=$?
    if [[ -z "$_opsgenome_last_cmd" ]]; then
        return
    fi

    local end_time
    end_time=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
    local duration=$(( end_time - _opsgenome_start_time ))
    if (( duration < 0 )); then duration=0; fi

    local current_cmd="$_opsgenome_last_cmd"
    _opsgenome_last_cmd=""

    # Redact in-process on client and transmit via secure Unix Domain Socket (never curl, never HTTP TCP)
    (
        python3 -m opsgenome.cli.client "$current_cmd" "$exit_code" "$duration" "$PWD" "$_opsgenome_sock" >/dev/null 2>&1 &
    )
}

# Register zsh hooks
autoload -Uz add-zsh-hook
add-zsh-hook preexec _opsgenome_preexec
add-zsh-hook precmd _opsgenome_precmd

# Interactive runner capturing full stdout/stderr with instant auto-fix capability
ops-run() {
    python3 -m opsgenome.cli.main run "$@"
}
alias opsrun="python3 -m opsgenome.cli.main run"
