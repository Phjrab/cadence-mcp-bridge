#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/bandwidth-qual-v1"
RUNTIME="$ROOT/bandwidth-qual-v1"
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || exit 64
case "$1" in run) [ "$#" -eq 2 ] && [[ "$2" = 50 || "$2" = 100 ]] || exit 64 ;;
  result) [ "$#" -eq 1 ] || exit 64 ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$RUNTIME" || exit 69
for dependency in bandwidth-qual-v1 native-mcp-v3 native-mcp-v2 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  if [ "$1" = result ]; then
    /usr/bin/python "$VERSION/helper.py" result
    exit
  fi
  GRID="$2"
  JOB="$RUNTIME/grid$GRID"
  /usr/bin/python "$VERSION/helper.py" begin "$GRID"
  /usr/bin/python "$VERSION/helper.py" reserve "$GRID"
  (
    cd "$JOB/netlist"
    ulimit -f 32768
    timeout 120 /home/buet/cadence/MMSIM121/tools/bin/spectre -format psfbin \
      -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
      >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
  )
  test "$(du -sk "$JOB" | cut -f1)" -le 122880
  (
    cd /home/buet/cds_work
    ulimit -f 2048
    timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
      -restore "$JOB/extract.ocn" -log "$JOB/ocean.log" \
      >"$JOB/ocean.stdout" 2>"$JOB/ocean.stderr"
  )
  /usr/bin/python "$VERSION/helper.py" finish "$GRID"
  test "$(du -sk "$JOB" | cut -f1)" -le 131072
) 9>"$ROOT/run.lock"
