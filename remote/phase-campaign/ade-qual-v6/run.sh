#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ade-qual-v6"
JOB="$ROOT/ade-qual-v6"
HELPER="$VERSION/helper.py"
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean
VIRTUOSO=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre
[ "$#" -eq 1 ] || exit 64
case "$1" in netlist|dc|status) ;; *) exit 64 ;; esac
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null || exit 69
(cd "$ROOT/phase-campaign/sim-mcp-v2" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
(cd "$ROOT/phase-campaign/role-v1" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
test ! -L "$ROOT/run.lock" || exit 69
if [ "$1" = status ]; then
  /usr/bin/python "$HELPER" status
  exit
fi
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  failure=netlist_failed
  trap 'code=$?; if [ -d "$JOB" ]; then /usr/bin/python "$HELPER" stage "$failure" || true; fi; exit "$code"' ERR
  if [ "$1" = netlist ]; then
    test ! -e "$JOB" && test ! -L "$JOB" || exit 69
    /usr/bin/python "$HELPER" prepare
    (
      cd /home/buet/cds_work
      ulimit -f 8192
      DISPLAY=:0 /usr/bin/xdpyinfo >/dev/null 2>&1
      timeout 180 "$VIRTUOSO" -display :0 -nocdsinit -replay "$VERSION/netlist.ocn" \
        -log "$JOB/netlist.log" > "$JOB/netlist.stdout" 2> "$JOB/netlist.stderr"
    )
    /usr/bin/python "$HELPER" netlist > "$JOB/netlist-result.json"
    test "$(du -sk "$JOB" | cut -f1)" -le 131072
    /usr/bin/python "$HELPER" stage netlisted
    cat "$JOB/netlist-result.json"
  else
    test "$(cat "$JOB/stage")" = netlisted || exit 69
    test ! -L "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf" || exit 69
    mkdir -p -m 700 "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
    failure=reservation_failed
    /usr/bin/python "$HELPER" stage reserving
    /usr/bin/python "$HELPER" reserve
    failure=simulator_failed
    /usr/bin/python "$HELPER" stage simulating
    (
      cd "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
      ulimit -f 32768
      timeout 120 "$SPECTRE" -format psfbin -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
        > "$JOB/spectre.stdout" 2> "$JOB/spectre.stderr"
    )
    failure=extraction_failed
    /usr/bin/python "$HELPER" stage extracting
    /usr/bin/python "$HELPER" extraction
    (
      cd /home/buet/cds_work
      ulimit -f 8192
      timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$JOB/extract.ocn" \
        -log "$JOB/extract.log" > "$JOB/extract.stdout" 2> "$JOB/extract.stderr"
    )
    failure=verification_failed
    /usr/bin/python "$HELPER" stage verifying
    /usr/bin/python "$HELPER" complete > "$JOB/result.json"
    test "$(du -sk "$JOB" | cut -f1)" -le 131072
    /usr/bin/python "$HELPER" stage succeeded
    cat "$JOB/result.json"
  fi
) 9>"$ROOT/run.lock"
