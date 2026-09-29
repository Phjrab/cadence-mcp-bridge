#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 1 ] || exit 64
case "$1" in baseline-resume) MODE=baseline ;; candidate) MODE=candidate ;; *) exit 64 ;; esac

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/dc-v2"
RUNTIME="$ROOT/wp14-copied-dc-v1"
HELPER="$VERSION/dc_helper.py"
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre

[ -x "$SPECTRE" ] && [ -f "$HELPER" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
test ! -L "$ROOT/run.lock" || exit 69

(
  flock -n 9 || exit 75
  before="$VERSION/.before.$$.tmp"
  trap 'rm -f "$before"' EXIT
  /usr/bin/python "$HELPER" check "$MODE" > /dev/null
  JOB="$RUNTIME/$MODE"
  if [ "$MODE" = candidate ]; then mkdir -m 700 "$JOB"; fi
  /usr/bin/python "$HELPER" prepare "$MODE" > "$before"
  chmod 600 "$before"
  mv -f "$before" "$JOB/before.json"

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
