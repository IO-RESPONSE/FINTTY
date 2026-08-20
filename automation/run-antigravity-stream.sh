#!/usr/bin/env bash
set -u
set -o pipefail

REPO=/home/nytr/nssmitty
AGY=/home/nytr/.local/bin/agy
PROMPT_FILE="$REPO/ANTIGRAVITY_RUN_PROMPT.md"
LOCK_FILE=/tmp/nssmitty-antigravity-stream.lock
LOG_DIR="$REPO/.antigravity-runs"
STOP_FILE="$REPO/.antigravity-stop"
COMPLETE_FILE="$REPO/.antigravity-complete"
DEADLINE_FILE="$REPO/.antigravity-deadline"
BACKOFF_FILE="$REPO/.antigravity-backoff"
STATUS_FILE="$REPO/.antigravity-runner-status"

SESSION_SECONDS=${SESSION_SECONDS:-14400}
PRINT_TIMEOUT=${PRINT_TIMEOUT:-230m}
NORMAL_DELAY=${NORMAL_DELAY:-60}
RATE_INITIAL=${RATE_INITIAL:-1800}
RATE_MAX=${RATE_MAX:-21600}
TRANSIENT_INITIAL=${TRANSIENT_INITIAL:-300}
TRANSIENT_MAX=${TRANSIENT_MAX:-3600}

mkdir -p "$LOG_DIR"

write_status() {
    local state=$1 message=${2:-}
    local tmp="${STATUS_FILE}.tmp"
    {
        printf 'state=%s\n' "$state"
        printf 'message=%s\n' "$message"
        printf 'updated_at=%s\n' "$(date --iso-8601=seconds)"
        printf 'pid=%s\n' "$$"
    } >"$tmp"
    mv "$tmp" "$STATUS_FILE"
}

deadline_reached() {
    local deadline
    [[ -r "$DEADLINE_FILE" ]] || return 1
    deadline=$(<"$DEADLINE_FILE")
    [[ "$deadline" =~ ^[0-9]+$ ]] || return 1
    (( $(date +%s) >= deadline ))
}

interruptible_sleep() {
    local remaining=$1 reason=$2 step
    while (( remaining > 0 )); do
        [[ ! -e "$STOP_FILE" && ! -e "$COMPLETE_FILE" ]] || return 1
        deadline_reached && return 1
        step=60
        (( remaining < step )) && step=$remaining
        write_status backoff "$reason; remaining=${remaining}s"
        sleep "$step"
        remaining=$((remaining - step))
    done
}

matches() {
    local pattern=$1 file=$2
    grep -Eiq "$pattern" "$file"
}

next_backoff() {
    local kind=$1 initial=$2 maximum=$3 stored_kind= stored= next
    if [[ -r "$BACKOFF_FILE" ]]; then
        read -r stored_kind stored <"$BACKOFF_FILE" || true
    fi
    if [[ "$stored_kind" == "$kind" && "$stored" =~ ^[0-9]+$ ]]; then
        next=$((stored * 2))
    else
        next=$initial
    fi
    (( next > maximum )) && next=$maximum
    printf '%s %s\n' "$kind" "$next" >"${BACKOFF_FILE}.tmp"
    mv "${BACKOFF_FILE}.tmp" "$BACKOFF_FILE"
    printf '%s\n' "$next"
}

with_jitter() {
    local base=$1 max=$((base / 10))
    (( max > 0 )) && base=$((base + RANDOM % (max + 1)))
    printf '%s\n' "$base"
}

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
trap 'write_status stopped "termination signal"; exit 0' TERM INT HUP

[[ -x "$AGY" ]] || { write_status fatal "agy not executable: $AGY"; exit 127; }
[[ -r "$PROMPT_FILE" ]] || { write_status fatal "prompt missing: $PROMPT_FILE"; exit 1; }
cd "$REPO" || exit 1

while true; do
    [[ ! -e "$STOP_FILE" ]] || { write_status paused "stop file present"; exit 0; }
    [[ ! -e "$COMPLETE_FILE" ]] || { write_status complete "completion marker present"; exit 0; }
    if deadline_reached; then
        write_status expired "deadline reached"
        touch "$STOP_FILE"
        exit 0
    fi

    run_id=$(date '+%Y%m%d-%H%M%S')
    log_file="$LOG_DIR/$run_id.log"
    started=$(date +%s)
    write_status running "session=$run_id"

    timeout --signal=TERM --kill-after=2m "${SESSION_SECONDS}s" \
        "$AGY" --new-project --sandbox --mode accept-edits \
        --output-format json --print-timeout "$PRINT_TIMEOUT" \
        --print "$(<"$PROMPT_FILE")" >>"$log_file" 2>&1
    rc=$?
    elapsed=$(($(date +%s) - started))
    printf '\nrunner_exit_code=%s\nelapsed_seconds=%s\nfinished_at=%s\n' \
        "$rc" "$elapsed" "$(date --iso-8601=seconds)" >>"$log_file"

    [[ ! -e "$STOP_FILE" && ! -e "$COMPLETE_FILE" ]] || continue

    if matches '"status"[[:space:]]*:[[:space:]]*"ERROR"' "$log_file"; then
        printf '%s agy-json-error rc=%s log=%s\n' "$(date --iso-8601=seconds)" "$rc" "$log_file" >>"$LOG_DIR/runner-error.log"
        interruptible_sleep 900 'AGY reported ERROR' || continue
        continue
    fi

    if matches '(^|[^0-9])429([^0-9]|$)|rate[ _-]?limit|quota.*exceeded|resource[_ ]exhausted|usage[ _-]?limit|too many requests|retry after' "$log_file"; then
        delay=$(with_jitter "$(next_backoff rate-limit "$RATE_INITIAL" "$RATE_MAX")")
        printf '%s rate-limit delay=%s log=%s\n' "$(date --iso-8601=seconds)" "$delay" "$log_file" >>"$LOG_DIR/runner-error.log"
        interruptible_sleep "$delay" 'rate limit' || continue
        continue
    fi

    if matches 'authentication required|not authenticated|login required|unauthorized|oauth.*(expired|failed|invalid)|credential.*expired' "$log_file"; then
        write_status authentication-required "see $log_file"
        printf '%s authentication failure log=%s\n' "$(date --iso-8601=seconds)" "$log_file" >>"$LOG_DIR/runner-error.log"
        touch "$STOP_FILE"
        exit 1
    fi

    if (( rc == 124 || rc == 137 )) || matches 'timed out|temporary failure|connection reset|network is unreachable|could not resolve|service unavailable|bad gateway|gateway timeout|internal server error' "$log_file"; then
        delay=$(with_jitter "$(next_backoff transient "$TRANSIENT_INITIAL" "$TRANSIENT_MAX")")
        printf '%s transient delay=%s rc=%s log=%s\n' "$(date --iso-8601=seconds)" "$delay" "$rc" "$log_file" >>"$LOG_DIR/runner-error.log"
        interruptible_sleep "$delay" 'transient failure' || continue
        continue
    fi

    if (( rc != 0 || elapsed < 5 )); then
        printf '%s unclassified rc=%s elapsed=%s log=%s\n' "$(date --iso-8601=seconds)" "$rc" "$elapsed" "$log_file" >>"$LOG_DIR/runner-error.log"
        interruptible_sleep 900 'unclassified or early exit' || continue
        continue
    fi

    rm -f -- "$BACKOFF_FILE"
    write_status restarting 'successful session completed'
    interruptible_sleep "$NORMAL_DELAY" 'normal restart' || continue
done
