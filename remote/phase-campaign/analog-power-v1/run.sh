#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/analog-power-v1"
RUNTIME="$ROOT/analog-power-v1"
[ "$#" -eq 1 ] || exit 64
case "$1" in read|result) ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$RUNTIME" || exit 69
for dependency in analog-power-v1 native-mcp-v3 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
if [ "$1" = result ]; then
  /usr/bin/python "$VERSION/helper.py" result
  exit
fi
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  /usr/bin/python "$VERSION/helper.py" begin
  (
    cd "$RUNTIME"
    ulimit -f 2048
    timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
      -restore "$RUNTIME/read.ocn" -log "$RUNTIME/ocean.log" \
      >"$RUNTIME/ocean.stdout" 2>"$RUNTIME/ocean.stderr"
  )
  /usr/bin/python "$VERSION/helper.py" finish
) 9>"$ROOT/run.lock"
