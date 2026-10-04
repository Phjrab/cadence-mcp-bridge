#!/bin/bash
set -euo pipefail
umask 077
[ "$#" -eq 0 ] || exit 64
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ade-pvt-prep-v1"
test ! -L "$ROOT/run.lock" || exit 69
for dependency in native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  ulimit -f 512
  /usr/bin/python "$VERSION/inventory.py"
) 9>"$ROOT/run.lock"
