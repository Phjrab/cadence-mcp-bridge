#!/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 0 ] || exit 64

ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/role-v2"
RUNTIME="$ROOT/wp14-role-discovery-v2"
HELPER="$VERSION/role_v2_helper.py"
SCRIPT="$ROOT/phase-campaign/role-v1/wp14-role-discovery.il"
VIRTUOSO=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ -x "$VIRTUOSO" ] && [ -f "$HELPER" ] && [ -f "$SCRIPT" ] || exit 69
command -v flock >/dev/null 2>&1 || exit 69
mkdir -m 700 "$RUNTIME"

(
  flock -n 9 || exit 75
  before="$RUNTIME/.before.$$.tmp"
  result="$RUNTIME/.result.$$.tmp"
  status="$RUNTIME/.status.$$.tmp"
  trap 'rm -f "$before" "$result" "$status"' EXIT

  /usr/bin/python "$HELPER" preflight > "$before"
  chmod 600 "$before"
  mv -f "$before" "$RUNTIME/before.json"

  if ! /usr/bin/python "$HELPER" gate > "$result"; then
    chmod 600 "$result"
    [ "$(wc -c < "$result")" -le 16384 ] || exit 69
    cat "$result"
    exit 69
  fi

  set +e
  (
    cd /home/buet/cds_work
    ulimit -f 2048
    timeout 90 "$VIRTUOSO" -nograph -nocdsinit -restore "$SCRIPT" \
      -log /dev/null 2> "$RUNTIME/skill.stderr"
  ) | /usr/bin/python "$HELPER" complete > "$result"
  component_status=("${PIPESTATUS[@]}")
  set -e
  printf 'virtuoso_exit=%s\nparser_exit=%s\n' \
    "${component_status[0]}" "${component_status[1]}" > "$status"
  chmod 600 "$status"
  mv -f "$status" "$RUNTIME/attempt-status.txt"
  chmod 600 "$RUNTIME/skill.stderr"
  [ "${component_status[0]}" -eq 0 ] && [ "${component_status[1]}" -eq 0 ] || exit 69

  chmod 600 "$result"
  [ "$(wc -c < "$result")" -le 16384 ] || exit 69
  mv -f "$result" "$RUNTIME/result.json"
  cat "$RUNTIME/result.json"
) 9> "$VERSION/read.lock"
