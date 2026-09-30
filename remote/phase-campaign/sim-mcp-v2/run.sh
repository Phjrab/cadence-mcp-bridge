#!/bin/bash
set -euo pipefail
umask 077

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/sim-mcp-v2"
JOBS="$ROOT/sim-mcp-v2-jobs"
HELPER="$VERSION/diagnostic.py"
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean

[ "$#" -eq 3 ] || exit 64
ACTION="$1"
ID="$2"
ANALYSIS="$3"
[[ "$ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || exit 64
case "$ANALYSIS" in dc|ac) ;; *) exit 64 ;; esac
case "$ACTION" in submit|status|result|worker) ;; *) exit 64 ;; esac
[ -x "$SPECTRE" ] && [ -x "$OCEAN" ] && [ -f "$HELPER" ] || exit 69
test ! -L "$ROOT/run.lock" && test ! -L "$JOBS" || exit 69
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null || exit 69
JOB="$JOBS/$ID"

stage() {
  printf '%s\n' "$1" > "$JOB/.stage.$$"
  mv -f "$JOB/.stage.$$" "$JOB/stage"
}

failed_stage() {
  local current
  current="$(cat "$JOB/stage" 2>/dev/null || true)"
  case "$current" in
    running) stage simulator_failed ;;
    extracting) stage extraction_failed ;;
    *) stage failed ;;
  esac
  rm -f "$JOBS/active"
}

if [ "$ACTION" = status ] || [ "$ACTION" = result ]; then
  [ -d "$JOB" ] && [ ! -L "$JOB" ] || exit 69
  /usr/bin/python "$HELPER" "$ACTION" "$ID" "$ANALYSIS"
  exit
fi

if [ "$ACTION" = submit ]; then
  (
    flock -n 8 || exit 75
    [ -d "$JOBS" ] && [ ! -L "$JOBS" ] || exit 69
    if [ -d "$JOB" ] && [ ! -L "$JOB" ]; then
      /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS"
      exit
    fi
    [ ! -e "$JOB" ] && [ ! -L "$JOB" ] && [ ! -e "$JOBS/active" ] || exit 75
    if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
    /usr/bin/python "$HELPER" preflight "$ID" "$ANALYSIS" >/dev/null
    mkdir -m 700 "$JOB"
    printf '{"analysis":"%s","revision_id":"wp14-copied-netlist-v1","operating_point_id":"candidate-320-702mv-v1"}\n' "$ANALYSIS" > "$JOB/request.json"
    stage queued
    printf '%s\n' "$ID" > "$JOBS/active"
    nohup "$VERSION/run.sh" worker "$ID" "$ANALYSIS" </dev/null >"$JOB/worker.stdout" 2>"$JOB/worker.stderr" &
    /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS"
  ) 8>"$JOBS/control.lock"
  exit
fi

[ -d "$JOB" ] && [ ! -L "$JOB" ] || exit 69
(
  flock -n 9 || exit 75
  trap failed_stage EXIT
  [ "$(cat "$JOBS/active")" = "$ID" ] || exit 69
  /usr/bin/python "$HELPER" prepare "$ID" "$ANALYSIS"
  /usr/bin/python "$HELPER" reserve "$ID" "$ANALYSIS"
  stage running
  (
    cd "$JOB"
    ulimit -f 32768
    timeout 120 "$SPECTRE" -format psfbin -raw psf =log spectre.log profile.scs > stdout.log 2> stderr.log
  )
  stage extracting
  sed "s|@JOB@|$JOB|g" "$VERSION/extract-$ANALYSIS.ocn" > "$JOB/extract.ocn"
  (
    cd /home/buet/cds_work
    ulimit -f 8192
    timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$JOB/extract.ocn" -log "$JOB/ocean.log" > "$JOB/ocean.stdout" 2> "$JOB/ocean.stderr"
  )
  /usr/bin/python "$HELPER" complete "$ID" "$ANALYSIS" > "$JOB/result.json"
  [ "$(wc -c < "$JOB/result.json")" -le 32768 ] || exit 69
  [ "$(du -sk "$JOB" | cut -f1)" -le 131072 ] || exit 69
  stage succeeded
  trap - EXIT
  rm -f "$JOBS/active"
) 9>"$ROOT/run.lock"
