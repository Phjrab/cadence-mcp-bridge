#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

RUNTIME="$CADENCE_MCP_ROOT/ade-profile-introspection"
HELPER="$CADENCE_MCP_ROOT/py26/ade_profile_introspection.py"
SCRIPT="$CADENCE_MCP_ROOT/discovery/ade-profile-introspection.il"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 0 ] || cadence_mcp_fail "fixed ADE introspection accepts no worker arguments" 64
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
mkdir -p "$RUNTIME" || cadence_mcp_fail "ADE introspection runtime unavailable" 73
chmod 700 "$RUNTIME"

before_temporary="$RUNTIME/.before.$$.tmp"
"$CADENCE_MCP_PYTHON" "$HELPER" preflight > "$before_temporary" \
    || cadence_mcp_fail "ADE introspection preflight failed" 69
chmod 600 "$before_temporary"
mv -f "$before_temporary" "$RUNTIME/before.json"

(
    cd /home/buet/cds_work || exit 73
    timeout 90 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" \
        -log "$RUNTIME/skill.log" \
        > "$RUNTIME/skill.stdout" 2> "$RUNTIME/skill.stderr"
) || cadence_mcp_fail "fixed read-only ADE OA inspection failed" 69

for log_file in "$RUNTIME/skill.log" "$RUNTIME/skill.stdout" "$RUNTIME/skill.stderr"; do
    [ -f "$log_file" ] || cadence_mcp_fail "ADE introspection log is unavailable" 69
    bounded="$log_file.bounded"
    tail -c 65536 "$log_file" > "$bounded" \
        || cadence_mcp_fail "ADE introspection log bounding failed" 69
    chmod 600 "$bounded"
    mv -f "$bounded" "$log_file"
done

"$CADENCE_MCP_PYTHON" "$HELPER" complete
