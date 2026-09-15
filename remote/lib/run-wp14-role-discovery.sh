#!/bin/bash

set -u
set -o pipefail
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

RUNTIME="$CADENCE_MCP_ROOT/wp14-role-discovery"
HELPER="$CADENCE_MCP_ROOT/py26/wp14_role_discovery.py"
SCRIPT="$CADENCE_MCP_ROOT/discovery/wp14-role-discovery.il"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 0 ] || cadence_mcp_fail "fixed WP-14 discovery accepts no arguments" 64
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
[ -f "$HELPER" ] || cadence_mcp_fail "WP-14 redaction helper is unavailable" 69
[ -f "$SCRIPT" ] || cadence_mcp_fail "WP-14 fixed SKILL is unavailable" 69
mkdir -p "$RUNTIME" || cadence_mcp_fail "WP-14 discovery runtime unavailable" 73
chmod 700 "$RUNTIME"

before_temporary="$RUNTIME/.before.$$.tmp"
result_temporary="$RUNTIME/.result.$$.tmp"

"$CADENCE_MCP_PYTHON" "$HELPER" preflight > "$before_temporary" \
    || cadence_mcp_fail "WP-14 discovery preflight failed" 69
chmod 600 "$before_temporary"
mv -f "$before_temporary" "$RUNTIME/before.json"

if ! "$CADENCE_MCP_PYTHON" "$HELPER" gate > "$result_temporary"; then
    chmod 600 "$result_temporary"
    [ "$(wc -c < "$result_temporary")" -le 16384 ] \
        || cadence_mcp_fail "WP-14 blocked output exceeded its bound" 69
    cat "$result_temporary"
    exit 69
fi

(
    cd /home/buet/cds_work || exit 73
    timeout 30 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" \
        -log /dev/null 2> /dev/null
) | "$CADENCE_MCP_PYTHON" "$HELPER" complete > "$result_temporary" \
    || cadence_mcp_fail "fixed WP-14 read-only discovery failed" 69

chmod 600 "$result_temporary"
[ "$(wc -c < "$result_temporary")" -le 16384 ] \
    || cadence_mcp_fail "WP-14 discovery output exceeded its bound" 69
mv -f "$result_temporary" "$RUNTIME/result.json"
cat "$RUNTIME/result.json"
