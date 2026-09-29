#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 0 ] || exit 64

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ac-scalar-v2"
RUNTIME="$ROOT/wp14-ac-scalars-v2"
HELPER="$VERSION/scalar_helper.py"
SCRIPT="$VERSION/extract.ocn"
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean

[ -x "$OCEAN" ] && [ -f "$HELPER" ] && [ -f "$SCRIPT" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
test ! -L "$ROOT/run.lock" || exit 69
mkdir -m 700 "$RUNTIME"

(
  flock -n 9 || exit 75
  /usr/bin/python "$HELPER" preflight > "$RUNTIME/before.json"
  chmod 600 "$RUNTIME/before.json"

  set +e
  (
    cd /home/buet/cds_work
    ulimit -f 8192
    timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$SCRIPT" \
      -log "$RUNTIME/ocean.log" > "$RUNTIME/stdout.log" 2> "$RUNTIME/stderr.log"
  )
  ocean_exit=$?
  set -e
  printf 'ocean_exit=%s\n' "$ocean_exit" > "$RUNTIME/attempt-status.txt"
  chmod 600 "$RUNTIME/attempt-status.txt"
  [ "$ocean_exit" -eq 0 ] || exit 69

  /usr/bin/python "$HELPER" complete > "$RUNTIME/result.json"
  chmod 600 "$RUNTIME/result.json"
  [ "$(wc -c < "$RUNTIME/result.json")" -le 16384 ] || exit 69
  cat "$RUNTIME/result.json"
) 9> "$ROOT/run.lock"
