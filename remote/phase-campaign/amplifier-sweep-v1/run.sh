#!/bin/bash
set -euo pipefail
umask 077
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/amplifier-sweep-v1"
JOBS="$ROOT/amplifier-sweep-v1-jobs"
HELPER="$VERSION/helper.py"
[ "$#" -ge 1 ] && [ "$#" -le 5 ] || exit 64
ACTION="$1"
case "$ACTION" in
  postflight) [ "$#" -eq 1 ] || exit 64 ;;
  reserve) [ "$#" -eq 5 ] || exit 64 ;;
  lookup|submit|status|result|effective|worker) [ "$#" -eq 2 ] || exit 64 ;;
  *) exit 64 ;;
esac
if [ "$ACTION" != postflight ]; then
  ID="$2"
  [[ "$ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || exit 64
  JOB="$JOBS/$ID"
fi
if [ "$ACTION" = reserve ]; then
  [[ "$3" = dc || "$3" = ac ]] || exit 64
  [[ "$4" = 0.319 || "$4" = 0.32 || "$4" = 0.321 ]] || exit 64
  [[ "$5" =~ ^[0-9a-f]{64}$ ]] || exit 64
fi
test ! -L "$ROOT/run.lock" && test ! -L "$JOBS" && test ! -L "$JOBS/control.lock" || exit 69
test -d "$JOBS" || exit 69
for dependency in amplifier-sweep-v1 bias-range-qual-v1 offset-read-v1 offset-qual-v1 slew-read-v2 slew-qual-v1 slew-qual-v2 slew-qual-v3 slew-qual-v4 bandwidth-qual-v1 fs-sizing-screen-02-v2 native-mcp-v3 native-mcp-v2 native-mcp-v1 native-candidate-v2 native-ac-tran-v4 native-ac-tran-v3 ade-qual-v6 sim-mcp-v2 role-v1; do
  (cd "$ROOT/phase-campaign/$dependency" && sha256sum -c manifest.sha256 >/dev/null) || exit 69
done
case "$ACTION" in
  lookup|status|effective) /usr/bin/python "$HELPER" "$ACTION" "$ID"; exit ;;
  submit)
    (flock -n 8 || exit 75
     /usr/bin/python "$HELPER" allow_start "$ID"
    ) 8>"$JOBS/control.lock"
    exit ;;
  result|postflight)
    (flock -n 9 || exit 75
     if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
     /usr/bin/python "$HELPER" "$@"
    ) 9>"$ROOT/run.lock"
    exit ;;
esac
if [ "$ACTION" = reserve ]; then
  (
    flock -n 8 || exit 75
    test ! -e "$JOB" && test ! -L "$JOB" || exit 69
    test ! -e "$JOBS/active" && test ! -L "$JOBS/active" || exit 75
    (
      flock -n 9 || exit 75
      if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi
      /usr/bin/python "$HELPER" prepare "$ID" "$3" "$4" "$5"
      /usr/bin/python "$HELPER" reserve "$ID"
      printf '%s\n' "$ID" > "$JOBS/active"
      # Same EDA open file description is inherited. No second execution ledger.
      nohup "$VERSION/run.sh" worker "$ID" 8>&- </dev/null >"$JOB/worker.stdout" 2>"$JOB/worker.stderr" &
      printf '%s\n' "$!" > "$JOB/worker.pid"
      /usr/bin/python "$HELPER" lookup "$ID"
    ) 9>"$ROOT/run.lock"
  ) 8>"$JOBS/control.lock"
  exit
fi
# Worker is only entered with the inherited EDA lease and exact owned job.
flock -n 9 || exit 75
test -d "$JOB" && test ! -L "$JOB" && test ! -L "$JOBS/active" || exit 69
[ "$(cat "$JOBS/active")" = "$ID" ] || exit 69
finish() {
  code=$?
  trap - EXIT
  if [ "$code" -ne 0 ]; then
    /usr/bin/python "$HELPER" stage "$ID" failed || exit 69
  fi
  [ "$(cat "$JOBS/active")" = "$ID" ] || exit 69
  # Release EDA before advertising completion; only our tiny worker lease is removed.
  flock -u 9
  rm -f "$JOBS/active"
  exit "$code"
}
trap finish EXIT
for _ in $(seq 1 60); do
  if [ -e "$JOB/launch" ] && [ -e "$JOB/worker.pid" ]; then break; fi
  sleep 1
done
test -f "$JOB/launch" && test ! -L "$JOB/launch" || exit 69
[ "$(cat "$JOB/launch")" = "$ID" ] || exit 69
/usr/bin/python "$HELPER" stage "$ID" running
(
  cd "$JOB/netlist"
  ulimit -f 32768
  timeout 120 /home/buet/cadence/MMSIM121/tools/bin/spectre -format psfbin \
    -raw "$JOB/psf" =log "$JOB/spectre.log" input.scs \
    >"$JOB/spectre.stdout" 2>"$JOB/spectre.stderr"
)
test "$(du -sk "$JOB" | cut -f1)" -le 114688
/usr/bin/python "$HELPER" stage "$ID" extracting
(
  cd /home/buet/cds_work
  ulimit -f 1024
  timeout 90 /home/buet/cadence/IC615/tools/dfII/bin/ocean -nograph -nocdsinit \
    -restore "$JOB/extract.ocn" -log "$JOB/ocean.log" \
    >"$JOB/ocean.stdout" 2>"$JOB/ocean.stderr"
)
/usr/bin/python "$HELPER" finish "$ID"
