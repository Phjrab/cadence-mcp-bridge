#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/ade-pvt-qual-v1"
JOBS="$ROOT/ade-pvt-qual-v1-jobs"
HELPER="$VERSION/helper.py"
VIRTUOSO=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean
[ "$#" -eq 4 ] || exit 64
ACTION="$1" ID="$2" ANALYSIS="$3" CORNER="$4"
[[ "$ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || exit 64
case "$CORNER" in FF|SS|FS|SF) ;; *) exit 64 ;; esac
case "$ANALYSIS" in dc|ac) ;; *) exit 64 ;; esac
case "$ACTION" in submit|status|result|worker|postflight) ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$JOBS" && test ! -L "$JOBS/control.lock" || exit 69
for dependency in ade-pvt-qual-v1 ade-pvt-prep-v4 ade-pvt-prep-v3 ade-pvt-prep-v2 ade-pvt-prep-v1 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
RECORD="$JOBS/$ID"
JOB="$RECORD/work"
if [ "$ACTION" = status ] || [ "$ACTION" = result ] || [ "$ACTION" = postflight ]; then
  if [ "$ACTION" = postflight ] && ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  /usr/bin/python "$HELPER" "$ACTION" "$ID" "$ANALYSIS" "$CORNER"
  exit
fi
if [ "$ACTION" = submit ]; then
  # Returning an existing ID never replays an uncertain or failed operation.
  if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
    /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER"
    exit
  fi
  (
    flock -n 8 || exit 75
    if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
      /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER"
      exit
    fi
    [ -d "$JOBS" ] && [ ! -e "$JOBS/active" ] && [ ! -L "$JOBS/active" ] || exit 75
    (
      flock -n 9 || exit 75
      if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
      DISPLAY=:0 /usr/bin/xdpyinfo >/dev/null 2>&1 || exit 69
      /usr/bin/python "$HELPER" preflight "$ID" "$ANALYSIS" "$CORNER" >/dev/null
      mkdir -m 700 "$RECORD"
      printf '{"analysis":"%s","corner":"%s","revision_id":"wp14-native-ade-v1","operating_point_id":"candidate-320-702mv-v1"}\n' "$ANALYSIS" "$CORNER" > "$RECORD/request.json"
      printf 'queued\n' > "$RECORD/stage"
      printf '%s\n' "$ID" > "$JOBS/active"
      # The worker inherits the shared EDA lock's open file description.
      nohup "$VERSION/run.sh" worker "$ID" "$ANALYSIS" "$CORNER" 8>&- </dev/null >"$RECORD/worker.stdout" 2>"$RECORD/worker.stderr" &
      printf '%s\n' "$!" > "$RECORD/worker.pid"
      /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER"
    ) 9>"$ROOT/run.lock"
  ) 8>"$JOBS/control.lock"
  exit
fi
flock -n 9 || exit 75
[ -d "$RECORD" ] && [ ! -L "$RECORD" ] && [ "$(cat "$JOBS/active")" = "$ID" ] || exit 69
[ "$(cat "$RECORD/stage")" = queued ] && [ ! -e "$JOB" ] && [ ! -L "$JOB" ] || exit 69
failure=netlist_failed
finish() {
  code=$?
  trap - EXIT
  if [ "$code" -ne 0 ]; then
    if [ -d "$JOB" ]; then
      /usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$failure" || exit 69
    else
      printf 'failed\n' > "$RECORD/stage"
    fi
  fi
  [ "$(cat "$JOBS/active")" = "$ID" ] || exit 69
  rm -f "$JOBS/active"
  exit "$code"
}
trap finish EXIT
ulimit -f 131072
/usr/bin/python "$HELPER" prepare "$ID" "$ANALYSIS" "$CORNER"
(
  cd /home/buet/cds_work
  ulimit -f 8192
  timeout 180 "$VIRTUOSO" -display :0 -nocdsinit -replay "$JOB/netlist.ocn" \
    -log "$JOB/netlist.log" >"$JOB/netlist.stdout" 2>"$JOB/netlist.stderr"
)
/usr/bin/python "$HELPER" netlist "$ID" "$ANALYSIS" "$CORNER" > "$JOB/netlist-result.json"
test "$(du -sk "$RECORD" | cut -f1)" -le 131072
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" netlisted
test ! -L "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
mkdir -p -m 700 "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
failure=reservation_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" reserving
/usr/bin/python "$HELPER" reserve "$ID" "$ANALYSIS" "$CORNER"
failure=simulator_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" simulating
(
  cd "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
  ulimit -f 32768
  timeout 120 "$SPECTRE" -format psfbin -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
    >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
)
failure=extraction_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" extracting
/usr/bin/python "$HELPER" extraction "$ID" "$ANALYSIS" "$CORNER"
(
  cd /home/buet/cds_work
  ulimit -f 8192
  timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$JOB/extract.ocn" \
    -log "$JOB/extract.log" >"$JOB/extract.stdout" 2>"$JOB/extract.stderr"
)
failure=verification_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" verifying
/usr/bin/python "$HELPER" complete "$ID" "$ANALYSIS" "$CORNER" > "$JOB/result.json"
test "$(du -sk "$RECORD" | cut -f1)" -le 131072
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" succeeded
