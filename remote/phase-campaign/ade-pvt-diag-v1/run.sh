#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ade-pvt-diag-v1"
RUNTIME="$ROOT/ade-pvt-diag-v1"
[ "$#" -eq 2 ] || exit 64
ACTION="$1" STEP="$2"
case "$ACTION" in read|result) ;; *) exit 64 ;; esac
case "$STEP" in probe|extract) ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$RUNTIME" || exit 69
for dependency in ade-pvt-diag-v1 ade-pvt-qual-v1 ade-pvt-prep-v4 ade-pvt-prep-v3 ade-pvt-prep-v2 ade-pvt-prep-v1 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
if [ "$ACTION" = result ]; then
  /usr/bin/python "$VERSION/helper.py" result "$STEP"
  exit
fi
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  /usr/bin/python "$VERSION/helper.py" begin "$STEP"
  (
    cd "$RUNTIME/$STEP"
    ulimit -f 2048
    timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
      -restore "$RUNTIME/$STEP/read.ocn" -log "$RUNTIME/$STEP/ocean.log" \
      >"$RUNTIME/$STEP/ocean.stdout" 2>"$RUNTIME/$STEP/ocean.stderr"
  )
  /usr/bin/python "$VERSION/helper.py" finish "$STEP"
) 9>"$ROOT/run.lock"
