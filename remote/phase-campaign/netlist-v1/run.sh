#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 0 ] || exit 64

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/netlist-v1"
RUNTIME="$ROOT/wp14-copied-netlist-v1"
HELPER="$VERSION/netlist_helper.py"
SCRIPT="$VERSION/copied-netlist.ocn"
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean

[ -x "$OCEAN" ] && [ -f "$HELPER" ] && [ -f "$SCRIPT" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
test ! -L "$ROOT/phase-campaign/eda.lock" || exit 69
mkdir -m 700 "$RUNTIME"
mkdir -m 700 "$RUNTIME/project"

(
  flock -n 9 || exit 75
  before="$RUNTIME/.before.$$.tmp"
  result="$RUNTIME/.result.$$.tmp"
  status="$RUNTIME/.status.$$.tmp"
  trap 'rm -f "$before" "$result" "$status"' EXIT

  /usr/bin/python "$HELPER" preflight > "$before"
  chmod 600 "$before"
  mv -f "$before" "$RUNTIME/before.json"
  /usr/bin/python "$HELPER" gate

  set +e
  (
    cd /home/buet/cds_work
    ulimit -f 8192
    timeout 180 "$OCEAN" -nograph -nocdsinit -restore "$SCRIPT" \
      -log "$RUNTIME/ocean.log" 2> "$RUNTIME/ocean.stderr"
  ) | /usr/bin/python "$HELPER" complete > "$result"
  component_status=("${PIPESTATUS[@]}")
  set -e
  printf 'ocean_exit=%s\nparser_exit=%s\n' \
    "${component_status[0]}" "${component_status[1]}" > "$status"
  chmod 600 "$status"
  mv -f "$status" "$RUNTIME/attempt-status.txt"
  [ "${component_status[0]}" -eq 0 ] && [ "${component_status[1]}" -eq 0 ] || exit 69

  chmod 600 "$result"
  [ "$(wc -c < "$result")" -le 16384 ] || exit 69
  mv -f "$result" "$RUNTIME/result.json"
  cat "$RUNTIME/result.json"
) 9> "$ROOT/phase-campaign/eda.lock"
