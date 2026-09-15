#!/bin/bash

set -eu
umask 077

[ "$#" -eq 0 ] || exit 64

ROOT=/home/buet/cds_work/.cadence_mcp
RUNTIME="$ROOT/ade-profile-introspection"
HELPER="$ROOT/py26/ade_profile_introspection.py"
SKILL="$ROOT/discovery/ade-profile-introspection.il"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
BEFORE="$RUNTIME/before.json"
RESULT="$RUNTIME/result.json"

[ -x "$VIRTUOSO_BIN" ] || exit 69
[ -f "$HELPER" ] && [ -f "$SKILL" ] || exit 69
mkdir -p "$RUNTIME"
chmod 700 "$RUNTIME"
rm -f "$RUNTIME/skill.stdout" "$RUNTIME/skill.stderr" "$RESULT.tmp"

"$CADENCE_MCP_PYTHON" "$HELPER" preflight > "$BEFORE.tmp"
chmod 600 "$BEFORE.tmp"
mv -f "$BEFORE.tmp" "$BEFORE"

(
    cd /home/buet/cds_work
    ulimit -f 2048
    timeout 90 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SKILL" \
        -log /dev/null > "$RUNTIME/skill.stdout" 2> "$RUNTIME/skill.stderr"
)
chmod 600 "$RUNTIME/skill.stdout" "$RUNTIME/skill.stderr"

grep -Eq '^MCP_ADE_OA[|]true[|][0-9]+[|][0-9]+[|][0-9]+$' "$RUNTIME/skill.stdout"
"$CADENCE_MCP_PYTHON" "$HELPER" complete > "$RESULT.tmp"
[ "$(wc -c < "$RESULT.tmp")" -le 65536 ] || exit 69
chmod 600 "$RESULT.tmp"
mv -f "$RESULT.tmp" "$RESULT"
cat "$RESULT"
