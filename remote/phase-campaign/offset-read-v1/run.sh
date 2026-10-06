#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/offset-read-v1"
[ "$#" -eq 1 ] && [ "$1" = result ] || exit 64
test ! -L "$ROOT/run.lock" || exit 69
for dependency in offset-read-v1 offset-qual-v1 slew-read-v1 slew-read-v2 slew-qual-v1 slew-qual-v2 slew-qual-v3 slew-qual-v4 bandwidth-qual-v1 fs-sizing-screen-02-v2 native-mcp-v3 native-mcp-v2 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  /usr/bin/python "$VERSION/helper.py" result
) 9>"$ROOT/run.lock"
