#!/bin/bash
set -euo pipefail
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/analog-power-v2"
[ "$#" -eq 1 ] && [ "$1" = result ] || exit 64
for dependency in analog-power-v2 analog-power-v1 native-mcp-v3 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
/usr/bin/python "$VERSION/helper.py" result
