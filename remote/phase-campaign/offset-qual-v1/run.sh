#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/offset-qual-v1"
RUNTIME="$ROOT/offset-qual-v1"
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || exit 64
case "$1" in run) [ "$#" -eq 2 ] && [[ "$2" = zero || "$2" = minus1 || "$2" = plus1 || "$2" = minus05 || "$2" = plus05 ]] || exit 64 ;;
  result|postflight) [ "$#" -eq 1 ] || exit 64 ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$RUNTIME" || exit 69
for dependency in offset-qual-v1 slew-read-v2 slew-qual-v1 slew-qual-v2 slew-qual-v3 slew-qual-v4 bandwidth-qual-v1 fs-sizing-screen-02-v2 native-mcp-v3 native-mcp-v2 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  if [ "$1" != run ]; then /usr/bin/python "$VERSION/helper.py" "$1"; exit; fi
  CASE="$2"
  JOB="$RUNTIME/$CASE"
  /usr/bin/python "$VERSION/helper.py" begin "$CASE"
  if [ "$CASE" != zero ]; then
    /usr/bin/python "$VERSION/helper.py" reserve "$CASE"
    (
      cd "$JOB/netlist"
      ulimit -f 32768
      timeout 120 /home/buet/cadence/MMSIM121/tools/bin/spectre -format psfbin \
        -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
        >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
    )
  fi
  test "$(du -sk "$JOB" | cut -f1)" -le 114688
  (
    cd /home/buet/cds_work
    ulimit -f 1024
    timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
      -restore "$JOB/extract.ocn" -log "$JOB/ocean.log" \
      >"$JOB/ocean.stdout" 2>"$JOB/ocean.stderr"
  )
  /usr/bin/python "$VERSION/helper.py" finish "$CASE"
  test "$(du -sk "$JOB" | cut -f1)" -le 131072
) 9>"$ROOT/run.lock"
