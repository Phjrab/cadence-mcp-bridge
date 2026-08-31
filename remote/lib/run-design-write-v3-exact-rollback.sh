#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

PLAN="$CADENCE_MCP_ROOT/config/design-write-v3-exact-conditional-rollback-plan.json"
HELPER="$CADENCE_MCP_ROOT/py26/v3_exact_rollback_json.py"
SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v3-exact-rollback.il"
REPORT=/home/buet/cds_work/.cadence_mcp/write-validation-v3/0b9bf93c-11e9-416f-9e4a-69b1060fbd8e/deep-forensic-v1/v3-deep-forensic-report.json
SOURCE=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
TARGET=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic
BACKUP=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 2 ] || cadence_mcp_fail "invalid V3 exact rollback invocation" 64
run_id=$1
origin=$2
cadence_mcp_validate_job_id "$run_id" || cadence_mcp_fail "invalid rollback run id" 64
case "$origin" in operator) ;; *) cadence_mcp_fail "invalid rollback origin" 64 ;; esac
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V3 rollback" 65
fi
for view in "$SOURCE" "$TARGET" "$BACKUP"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed rollback cellview is unavailable" 69
done
blocking=$(find "$SOURCE" "$TARGET" "$BACKUP" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) -print -quit)
[ -z "$blocking" ] || cadence_mcp_fail "blocking rollback artifact is present" 65
blocking=$(find "$TARGET" "$BACKUP" -maxdepth 1 -name 'sch.oa-' -print -quit)
[ -z "$blocking" ] || cadence_mcp_fail "V3 rollback artifact is present" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE") || cadence_mcp_fail "source fingerprint failed" 70
target_before=$(fingerprint_tree "$TARGET") || cadence_mcp_fail "target fingerprint failed" 70
backup_before=$(fingerprint_tree "$BACKUP") || cadence_mcp_fail "backup fingerprint failed" 70
report_hash=$(sha256sum "$REPORT" | cut -d ' ' -f 1) \
    || cadence_mcp_fail "forensic report fingerprint failed" 70
"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" preflight "$source_before" "$target_before" \
    "$backup_before" "$report_hash" || cadence_mcp_fail "BLOCKED_PLAN_OR_STATE_MISMATCH" 65

evidence_root="$CADENCE_MCP_ROOT/write-rollback-v3"
mkdir -p "$evidence_root" || cadence_mcp_fail "rollback evidence root creation failed" 73
chmod 700 "$evidence_root" || cadence_mcp_fail "rollback evidence root permission failed" 73
runtime="$evidence_root/$run_id"
[ ! -e "$runtime" ] || cadence_mcp_fail "rollback run already exists" 65
mkdir -m 700 "$runtime" || cadence_mcp_fail "rollback runtime creation failed" 73
stdout_file="$runtime/skill.stdout"
stderr_file="$runtime/skill.stderr"
log_file="$runtime/skill.log"
manifest="$runtime/rollback-manifest.json"
audit="$CADENCE_MCP_ROOT/audit/v3-rollback-events.jsonl"
(
    cd /home/buet/cds_work || exit 73
    timeout 180 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" -log "$log_file" \
        > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V3 rollback SKILL failed" 70

if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "Virtuoso remained active after V3 rollback" 70
fi
remaining=$(find "$SOURCE" "$TARGET" "$BACKUP" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) -print -quit)
[ -z "$remaining" ] || cadence_mcp_fail "rollback artifact remains" 70
source_after=$(fingerprint_tree "$SOURCE") || cadence_mcp_fail "source final fingerprint failed" 70
target_after=$(fingerprint_tree "$TARGET") || cadence_mcp_fail "target final fingerprint failed" 70
backup_after=$(fingerprint_tree "$BACKUP") || cadence_mcp_fail "backup final fingerprint failed" 70

"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" finalize "$run_id" "$stdout_file" \
    "$source_before" "$source_after" "$target_before" "$target_after" \
    "$backup_before" "$backup_after" "$report_hash" "$origin" "$(id -un)" \
    "$audit" "$manifest"
