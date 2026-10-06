#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/slew-qual-v4"
RUNTIME="$ROOT/slew-qual-v3"
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || exit 64
case "$1" in run) [ "$#" -eq 2 ] && [[ "$2" = coarse || "$2" = medium || "$2" = fine || "$2" = fast ]] || exit 64 ;;
  result|postflight|recover-coarse) [ "$#" -eq 1 ] || exit 64 ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$RUNTIME" || exit 69
for dependency in slew-qual-v1 slew-qual-v2 slew-qual-v3 slew-qual-v4 bandwidth-qual-v1 fs-sizing-screen-02-v2 native-mcp-v3 native-mcp-v2 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  if [ "$1" = recover-coarse ]; then
    /usr/bin/python "$VERSION/helper.py" finish coarse
    exit
  fi
  if [ "$1" != run ]; then
    /usr/bin/python "$VERSION/helper.py" "$1"
    exit
  fi
  CASE="$2"
  JOB="$RUNTIME/$CASE"
  /usr/bin/python "$VERSION/helper.py" begin "$CASE"
  /usr/bin/python "$VERSION/helper.py" reserve "$CASE"
  (
    cd "$JOB/netlist"
    ulimit -f 32768
    timeout 120 /home/buet/cadence/MMSIM121/tools/bin/spectre -format psfbin \
      -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
      >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
  )
  test "$(du -sk "$JOB" | cut -f1)" -le 114688
  (
    cd /home/buet/cds_work
    ulimit -f 65536
    timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
      -restore "$JOB/extract.ocn" -log "$JOB/ocean.log" \
      >"$JOB/ocean.stdout" 2>"$JOB/ocean.stderr"
  )
  /usr/bin/python "$VERSION/helper.py" finish "$CASE"
  test "$(du -sk "$JOB" | cut -f1)" -le 131072
) 9>"$ROOT/run.lock"
