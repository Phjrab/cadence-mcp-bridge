#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/bias-headroom-v2"
JOBS="$ROOT/bias-headroom-v1-jobs"
HELPER="$VERSION/helper.py"
VIRTUOSO=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SPECTRE=/home/buet/cadence/MMSIM121/tools/bin/spectre
OCEAN=/home/buet/cadence/IC615/tools/dfII/bin/ocean
[ "$#" -eq 5 ] || exit 64
ACTION="$1" ID="$2" ANALYSIS="$3" CORNER="$4" PAIR="$5"
[[ "$ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || exit 64
case "$CORNER" in NN|FF|SS|FS|SF) ;; *) exit 64 ;; esac
case "$PAIR" in 0|1|2|3) ;; *) exit 64 ;; esac
case "$ANALYSIS" in dc|ac) ;; *) exit 64 ;; esac
case "$ACTION" in submit|status|result|worker|postflight|selection|recover) ;; *) exit 64 ;; esac
test ! -L "$ROOT/run.lock" && test ! -L "$JOBS" && test ! -L "$JOBS/control.lock" || exit 69
for dependency in bias-headroom-v2 native-mcp-v2 ade-pvt-qual-v1 ade-pvt-prep-v4 ade-pvt-prep-v3 ade-pvt-prep-v2 ade-pvt-prep-v1 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
RECORD="$JOBS/$ID"
JOB="$RECORD/work"
if [ "$ACTION" = recover ]; then
  [ "$ID" = 222b32e0-e48d-4f28-8acb-bbb5e86708f6 ] && [ "$ANALYSIS:$CORNER:$PAIR" = dc:FF:0 ] || exit 64
  (
    flock -n 9 || exit 75
    if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
    [ ! -e "$JOBS/active" ] && [ ! -L "$JOBS/active" ] || exit 75
    /usr/bin/python "$HELPER" recovery_begin "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
    RECOVERY="$RECORD/recovery-v2"
    (cd /home/buet/cds_work
      ulimit -f 8192
      timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$RECOVERY/extract.ocn" -log "$RECOVERY/extract.log" >"$RECOVERY/extract.stdout" 2>"$RECOVERY/extract.stderr")
    /usr/bin/python "$HELPER" recovery_finish "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
  ) 9>"$ROOT/run.lock"
  exit
fi
if [ "$ACTION" = status ] || [ "$ACTION" = result ] || [ "$ACTION" = postflight ] || [ "$ACTION" = selection ]; then
  if [ "$ACTION" = postflight ] && ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
  /usr/bin/python "$HELPER" "$ACTION" "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
  exit
fi
if [ "$ACTION" = submit ]; then
  # Returning an existing ID never replays an uncertain or failed operation.
  if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
    /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
    exit
  fi
  (
    flock -n 8 || exit 75
    if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
      /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
      exit
    fi
    [ -d "$JOBS" ] && [ ! -e "$JOBS/active" ] && [ ! -L "$JOBS/active" ] || exit 75
    (
      flock -n 9 || exit 75
      if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
      DISPLAY=:0 /usr/bin/xdpyinfo >/dev/null 2>&1 || exit 69
      /usr/bin/python "$HELPER" preflight "$ID" "$ANALYSIS" "$CORNER" "$PAIR" >/dev/null
      mkdir -m 700 "$RECORD"
      printf '{"analysis":"%s","corner":"%s","revision_id":"wp14-native-ade-v1","operating_point_id":"bias-headroom-four-pairs-v1","pair_index":%s}\n' "$ANALYSIS" "$CORNER" "$PAIR" > "$RECORD/request.json"
      printf 'queued\n' > "$RECORD/stage"
      printf '%s\n' "$ID" > "$JOBS/active"
      # The worker inherits the shared EDA lock's open file description.
      nohup "$VERSION/run.sh" worker "$ID" "$ANALYSIS" "$CORNER" "$PAIR" 8>&- </dev/null >"$RECORD/worker.stdout" 2>"$RECORD/worker.stderr" &
      printf '%s\n' "$!" > "$RECORD/worker.pid"
      /usr/bin/python "$HELPER" status "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
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
      /usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" "$failure" || exit 69
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
/usr/bin/python "$HELPER" prepare "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
(
  cd /home/buet/cds_work
  ulimit -f 8192
  timeout 180 "$VIRTUOSO" -display :0 -nocdsinit -replay "$JOB/netlist.ocn" \
    -log "$JOB/netlist.log" >"$JOB/netlist.stdout" 2>"$JOB/netlist.stderr"
)
/usr/bin/python "$HELPER" netlist "$ID" "$ANALYSIS" "$CORNER" "$PAIR" > "$JOB/netlist-result.json"
test "$(du -sk "$RECORD" | cut -f1)" -le 131072
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" netlisted
test ! -L "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
mkdir -p -m 700 "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"
failure=reservation_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" reserving
/usr/bin/python "$HELPER" reserve "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
failure=simulator_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" simulating
(
  cd "$JOB/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
  ulimit -f 32768
  timeout 120 "$SPECTRE" -format psfbin -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
    >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
)
failure=extraction_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" extracting
/usr/bin/python "$HELPER" extraction "$ID" "$ANALYSIS" "$CORNER" "$PAIR"
(
  cd /home/buet/cds_work
  ulimit -f 8192
  timeout 90 "$OCEAN" -nograph -nocdsinit -restore "$JOB/extract.ocn" \
    -log "$JOB/extract.log" >"$JOB/extract.stdout" 2>"$JOB/extract.stderr"
)
failure=verification_failed
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" verifying
/usr/bin/python "$HELPER" complete "$ID" "$ANALYSIS" "$CORNER" "$PAIR" > "$JOB/result.json"
test "$(du -sk "$RECORD" | cut -f1)" -le 131072
/usr/bin/python "$HELPER" stage "$ID" "$ANALYSIS" "$CORNER" "$PAIR" succeeded
