#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 1 ] || exit 64
case "$1" in baseline|midpoint) MODE="$1" ;; *) exit 64 ;; esac

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ac-sweep-two-point-v1"
JOB_ROOT="$ROOT/wp14-ac-sweep-two-point-v1"
JOB="$JOB_ROOT/$MODE"
HELPER="$VERSION/ac_helper.py"
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre

[ -x "$SPECTRE" ] && [ -f "$HELPER" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
test ! -L "$ROOT/run.lock" || exit 69

(
  flock -n 9 || exit 75
  /usr/bin/python "$HELPER" check "$MODE" > /dev/null
  if [ ! -d "$JOB_ROOT" ]; then mkdir -m 700 "$JOB_ROOT"; fi
  mkdir -m 700 "$JOB"
  before="$VERSION/.before.$$.tmp"
  trap 'rm -f "$before"' EXIT
  /usr/bin/python "$HELPER" prepare "$MODE" > "$before"
  chmod 600 "$before"
  mv "$before" "$JOB/before.json"

  set +e
  (
    cd "$JOB"
    ulimit -f 16384
    timeout 120 "$SPECTRE" -format psfbin -raw psf =log spectre.log profile.scs \
      > stdout.log 2> stderr.log
  )
  spectre_exit=$?
  set -e
  printf 'spectre_exit=%s\n' "$spectre_exit" > "$JOB/attempt-status.txt"
  chmod 600 "$JOB/attempt-status.txt"
  [ "$spectre_exit" -eq 0 ] || exit 69

  /usr/bin/python "$HELPER" complete "$MODE" > "$JOB/result.json"
  chmod 600 "$JOB/result.json"
  [ "$(wc -c < "$JOB/result.json")" -le 16384 ] || exit 69
  cat "$JOB/result.json"
) 9> "$ROOT/run.lock"
