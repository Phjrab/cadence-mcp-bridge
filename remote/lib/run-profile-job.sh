#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

SPECTRE_BIN=/home/buet/cadence/MMSIM121/tools/bin/spectre

[ "$#" -eq 1 ] || cadence_mcp_fail "worker requires one job id" 64
job_id=$1
cadence_mcp_validate_job_id "$job_id" || cadence_mcp_fail "invalid job id" 64
job_dir=$(cadence_mcp_job_dir "$job_id") || cadence_mcp_fail "invalid job id" 64
[ -d "$job_dir" ] || cadence_mcp_fail "job not found" 66
[ -f "$job_dir/artifacts/profile.scs" ] || cadence_mcp_fail "profile netlist unavailable" 69
[ -f "$job_dir/artifacts/run-manifest.json" ] || cadence_mcp_fail "profile manifest unavailable" 69

cancel_job() {
    cadence_mcp_atomic_status "$job_id" cancelled "profile job cancelled"
    cadence_mcp_atomic_result "$job_id" cancelled 143 0 0 0 "profile job cancelled"
    origin=$(cadence_mcp_job_origin "$job_dir")
    actor=$(cadence_mcp_job_actor "$job_dir")
    cadence_mcp_audit job_cancelled "$job_id" "$origin" "$actor" \
        || cadence_mcp_fail "audit write failed" 70
    exit 0
}

trap cancel_job TERM INT HUP

exec 9> "$CADENCE_MCP_ROOT/run.lock"
flock 9

origin=$(cadence_mcp_job_origin "$job_dir") \
    || cadence_mcp_fail "job origin unavailable" 69
actor=$(cadence_mcp_job_actor "$job_dir") \
    || cadence_mcp_fail "job actor unavailable" 69
cadence_mcp_audit job_started "$job_id" "$origin" "$actor" \
    || cadence_mcp_fail "audit write failed" 70

if [ -f "$job_dir/cancel.request" ]; then
    cancel_job
fi

cadence_mcp_atomic_status "$job_id" running "allowlisted profile simulation running"
cd "$job_dir/artifacts" || cadence_mcp_fail "job artifact directory unavailable" 70
timeout 60 "$SPECTRE_BIN" -format psfbin -raw profile.raw =log profile.log profile.scs \
    > "$job_dir/stdout.log" 2> "$job_dir/stderr.log"
exit_code=$?

summary=$(grep 'spectre completes with' profile.log 2>/dev/null | tail -1)
errors=$(printf '%s\n' "$summary" | sed -n 's/.*completes with \([0-9][0-9]*\) errors.*/\1/p')
warnings=$(printf '%s\n' "$summary" | sed -n 's/.*errors, \([0-9][0-9]*\) warnings.*/\1/p')
notices=$(printf '%s\n' "$summary" | sed -n 's/.*warnings, and \([0-9][0-9]*\) notices*.*/\1/p')
[ -n "$errors" ] || errors=-1
[ -n "$warnings" ] || warnings=-1
[ -n "$notices" ] || notices=-1
[ -n "$summary" ] || summary="Spectre profile completion summary unavailable"

if [ "$exit_code" -eq 0 ] && [ "$errors" -eq 0 ] && [ "$warnings" -eq 0 ]; then
    final_state=succeeded
else
    final_state=failed
fi

cadence_mcp_atomic_result \
    "$job_id" "$final_state" "$exit_code" "$errors" "$warnings" "$notices" "$summary"
cadence_mcp_atomic_status "$job_id" "$final_state" "$summary"
cadence_mcp_audit job_finished "$job_id" "$origin" "$actor" \
    || cadence_mcp_fail "audit write failed" 70
