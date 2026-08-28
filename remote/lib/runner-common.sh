#!/bin/bash

CADENCE_MCP_ROOT=/home/buet/cds_work/.cadence_mcp
CADENCE_MCP_JOBS_ROOT="$CADENCE_MCP_ROOT/jobs"
CADENCE_MCP_PYTHON=/usr/bin/python
CADENCE_MCP_JSON_HELPER="$CADENCE_MCP_ROOT/py26/result_json.py"
CADENCE_MCP_PROFILE=spectre-smoke
CADENCE_MCP_JOB_ID_PATTERN='^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'

cadence_mcp_fail() {
    printf '%s\n' "$1" >&2
    exit "${2:-70}"
}

cadence_mcp_validate_job_id() {
    [ "$#" -eq 1 ] || return 1
    [[ "$1" =~ $CADENCE_MCP_JOB_ID_PATTERN ]]
}

cadence_mcp_job_dir() {
    cadence_mcp_validate_job_id "$1" || return 1
    printf '%s/%s\n' "$CADENCE_MCP_JOBS_ROOT" "$1"
}

cadence_mcp_utc_now() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

cadence_mcp_ensure_layout() {
    umask 077
    mkdir -p "$CADENCE_MCP_ROOT" "$CADENCE_MCP_JOBS_ROOT"
    chmod 700 "$CADENCE_MCP_ROOT" "$CADENCE_MCP_JOBS_ROOT"
}

cadence_mcp_atomic_status() {
    job_id=$1
    state=$2
    message=$3
    job_dir=$(cadence_mcp_job_dir "$job_id") || cadence_mcp_fail "invalid job id" 64
    temporary="$job_dir/.status.$$.tmp"
    "$CADENCE_MCP_PYTHON" "$CADENCE_MCP_JSON_HELPER" status \
        "$job_id" "$state" "$CADENCE_MCP_PROFILE" "$(cadence_mcp_utc_now)" "$message" \
        > "$temporary" || cadence_mcp_fail "status serialization failed" 70
    chmod 600 "$temporary"
    mv -f "$temporary" "$job_dir/status.json"
}

cadence_mcp_atomic_result() {
    job_id=$1
    state=$2
    exit_code=$3
    errors=$4
    warnings=$5
    notices=$6
    summary=$7
    job_dir=$(cadence_mcp_job_dir "$job_id") || cadence_mcp_fail "invalid job id" 64
    temporary="$job_dir/.result.$$.tmp"
    "$CADENCE_MCP_PYTHON" "$CADENCE_MCP_JSON_HELPER" result \
        "$job_dir" "$job_id" "$state" "$exit_code" "$errors" "$warnings" "$notices" \
        "$summary" > "$temporary" || cadence_mcp_fail "result serialization failed" 70
    chmod 600 "$temporary"
    mv -f "$temporary" "$job_dir/result.json"
}

cadence_mcp_worker_matches() {
    job_dir=$1
    [ -f "$job_dir/pid" ] && [ -f "$job_dir/pgid" ] && [ -f "$job_dir/start_marker" ] \
        || return 1
    pid=$(cat "$job_dir/pid")
    pgid=$(cat "$job_dir/pgid")
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [[ "$pgid" =~ ^[1-9][0-9]*$ ]] \
        || return 1
    [ "$pid" = "$pgid" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    current_pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
    [ "$current_pgid" = "$pgid" ] || return 1
    process_state=$(ps -o stat= -p "$pid" | tr -d ' ')
    case "$process_state" in Z*|"") return 1 ;; esac
    stored_marker=$(cat "$job_dir/start_marker")
    current_marker=$(ps -o lstart= -p "$pid" | sed 's/^ *//;s/ *$//')
    [ -n "$stored_marker" ] && [ "$stored_marker" = "$current_marker" ]
}
