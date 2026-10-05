#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/sweep-mcp-v2"
JOBS="$ROOT/sim-mcp-v2-jobs"
[ "$#" -eq 2 ] || exit 64
case "$1" in reserve|lookup|effective) ;; *) exit 64 ;; esac
[[ "$2" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || exit 64
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null || exit 69
[ -d "$JOBS" ] && [ ! -L "$JOBS" ] || exit 69
(
  flock -x 9
  /usr/bin/python "$VERSION/budget.py" "$1" "$2"
) 9>"$ROOT/run.lock"
