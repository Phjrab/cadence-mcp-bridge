#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 1 ] || exit 64
case "$1" in positive|negative) ;; *) exit 64 ;; esac
MODE="$1"

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/differential-dc-scalars-v1"
RUNTIME_ROOT="$ROOT/wp14-differential-dc-scalars-v1"
RUNTIME="$RUNTIME_ROOT/$MODE"
HELPER="$VERSION/scalar_helper.py"
SCRIPT="$VERSION/extract-$MODE.ocn"
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean

[ -x "$OCEAN" ] && [ -f "$HELPER" ] && [ -f "$SCRIPT" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
test ! -L "$ROOT/run.lock" || exit 69
if [ "$MODE" = positive ]; then
  test ! -e "$RUNTIME_ROOT" && test ! -L "$RUNTIME_ROOT" || exit 69
  mkdir -m 700 "$RUNTIME_ROOT"
else
  test -d "$RUNTIME_ROOT/positive" && test -s "$RUNTIME_ROOT/positive/result.json" || exit 69
  test ! -e "$RUNTIME" && test ! -L "$RUNTIME" || exit 69
fi
mkdir -m 700 "$RUNTIME"

(
  flock -n 9 || exit 75
  /usr/bin/python "$HELPER" preflight "$MODE" > "$RUNTIME/before.json"
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

  /usr/bin/python "$HELPER" complete "$MODE" > "$RUNTIME/result.json"
  chmod 600 "$RUNTIME/result.json"
  [ "$(wc -c < "$RUNTIME/result.json")" -le 16384 ] || exit 69
  cat "$RUNTIME/result.json"
) 9> "$ROOT/run.lock"
