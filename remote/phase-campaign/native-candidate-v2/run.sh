#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/native-candidate-v2"
[ "$#" -eq 2 ] || exit 64
case "$1:$2" in recover:ac|netlist:tran|simulate:tran|status:ac|status:tran|postflight:ac) ;; *) exit 64 ;; esac
ANALYSIS="$2"
JOB="$ROOT/native-candidate-v2-$ANALYSIS"
HELPER="$VERSION/helper.py"
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean
VIRTUOSO=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null || exit 69
for predecessor in ade-qual-v6 sim-mcp-v2 role-v1 native-ac-tran-v3 native-ac-tran-v4 native-candidate-v1; do
  (cd "$ROOT/phase-campaign/$predecessor" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
test ! -L "$ROOT/run.lock" || exit 69
if [ "$1" = postflight ] || [ "$1" = status ]; then
  /usr/bin/python "$HELPER" "$1" "$ANALYSIS"
  exit
fi
(
  flock -n 9 || exit 75
  if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  failure=netlist_failed
  trap 'code=$?; if [ -d "$JOB" ]; then /usr/bin/python "$HELPER" stage "$ANALYSIS" "$failure" || true; fi; exit "$code"' ERR
  if [ "$1" = netlist ]; then
    test ! -e "$JOB" && test ! -L "$JOB" || exit 69
    /usr/bin/python "$HELPER" prepare "$ANALYSIS"
    (
      cd /home/buet/cds_work
      ulimit -f 8192
      DISPLAY=:0 /usr/bin/xdpyinfo >/dev/null 2>&1
      timeout 180 "$VIRTUOSO" -display :0 -nocdsinit -replay "$VERSION/netlist-tran.ocn" \
        -log "$JOB/netlist.log" > "$JOB/netlist.stdout" 2> "$JOB/netlist.stderr"
    )
    /usr/bin/python "$HELPER" netlist "$ANALYSIS" > "$JOB/netlist-result.json"
    test "$(du -sk "$JOB" | cut -f1)" -le 131072
    /usr/bin/python "$HELPER" stage "$ANALYSIS" netlisted
    cat "$JOB/netlist-result.json"
  else
    if [ "$1" = recover ]; then
      failure=extraction_failed
      /usr/bin/python "$HELPER" recover ac
    else
      test "$(cat "$JOB/stage")" = netlisted || exit 69
      test ! -L "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf" || exit 69
      mkdir -p -m 700 "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
      failure=reservation_failed
      /usr/bin/python "$HELPER" stage tran reserving
      /usr/bin/python "$HELPER" reserve tran
      failure=simulator_failed
      /usr/bin/python "$HELPER" stage tran simulating
      (
        cd "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
        ulimit -f 32768
        timeout 120 "$SPECTRE" -format psfbin -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
          > "$JOB/spectre.stdout" 2> "$JOB/spectre.stderr"
      )
      failure=extraction_failed
      /usr/bin/python "$HELPER" stage tran extracting
    fi
    /usr/bin/python "$HELPER" extraction "$ANALYSIS"
    (
      cd /home/buet/cds_work
      ulimit -f 8192
      timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$JOB/extract.ocn" \
        -log "$JOB/extract.log" > "$JOB/extract.stdout" 2> "$JOB/extract.stderr"
    )
    failure=verification_failed
    /usr/bin/python "$HELPER" stage "$ANALYSIS" verifying
    /usr/bin/python "$HELPER" complete "$ANALYSIS" > "$JOB/result.json"
    test "$(du -sk "$JOB" | cut -f1)" -le 131072
    /usr/bin/python "$HELPER" stage "$ANALYSIS" succeeded
    cat "$JOB/result.json"
  fi
) 9>"$ROOT/run.lock"
