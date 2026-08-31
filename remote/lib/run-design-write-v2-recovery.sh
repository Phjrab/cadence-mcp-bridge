#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
PRESERVED_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic
TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic
BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic
POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
WRITE_HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
RECOVERY_HELPER="$CADENCE_MCP_ROOT/py26/v2_recovery_json.py"
FORENSIC_SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v2-forensic.il"
ROLLBACK_SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v2-rollback.il"
EVIDENCE_ROOT="$CADENCE_MCP_ROOT/write-validation/e55c7e81-cf20-4d5e-b2d9-67dae0ddcd1b"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 1 ] || cadence_mcp_fail "invalid V2 recovery invocation" 64
mode=$1
case "$mode" in forensic|rollback) ;; *) cadence_mcp_fail "invalid V2 recovery mode" 64 ;; esac

[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V2 recovery" 65
fi
"$CADENCE_MCP_PYTHON" "$WRITE_HELPER" "$POLICY" source-check \
    || cadence_mcp_fail "source master or artifact check failed" 65
for view in "$SOURCE_VIEW" "$PRESERVED_VIEW" "$TARGET_VIEW" "$BACKUP_VIEW"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed V2 recovery cellview is unavailable" 69
done
blocking_artifact=$(find "$TARGET_VIEW" "$BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "V2 recovery artifact is present" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source recovery fingerprint failed" 70
preserved_before=$(fingerprint_tree "$PRESERVED_VIEW") \
    || cadence_mcp_fail "preserved V1 recovery fingerprint failed" 70
target_before=$(fingerprint_tree "$TARGET_VIEW") \
    || cadence_mcp_fail "V2 target recovery fingerprint failed" 70
backup_before=$(fingerprint_tree "$BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup recovery fingerprint failed" 70

runtime="$EVIDENCE_ROOT/recovery-$mode-v2"
[ ! -e "$runtime" ] || cadence_mcp_fail "V2 recovery runtime already exists" 65
mkdir -m 700 "$runtime" || cadence_mcp_fail "V2 recovery runtime creation failed" 73
stdout_file="$runtime/skill.stdout"
stderr_file="$runtime/skill.stderr"
log_file="$runtime/skill.log"
case "$mode" in
    forensic) script=$FORENSIC_SCRIPT ;;
    rollback) script=$ROLLBACK_SCRIPT ;;
esac
(
    cd /home/buet/cds_work || exit 73
    timeout 180 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$script" -log "$log_file" \
        > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V2 recovery SKILL failed" 70

remaining_artifact=$(find "$TARGET_VIEW" "$BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "V2 recovery artifact remains" 70
source_after=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source post-recovery fingerprint failed" 70
preserved_after=$(fingerprint_tree "$PRESERVED_VIEW") \
    || cadence_mcp_fail "preserved V1 post-recovery fingerprint failed" 70
target_after=$(fingerprint_tree "$TARGET_VIEW") \
    || cadence_mcp_fail "V2 target post-recovery fingerprint failed" 70
backup_after=$(fingerprint_tree "$BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup post-recovery fingerprint failed" 70

case "$mode" in
    forensic)
        "$CADENCE_MCP_PYTHON" "$RECOVERY_HELPER" forensic "$stdout_file" \
            "$source_before" "$source_after" "$preserved_before" "$preserved_after" \
            "$target_before" "$target_after" "$backup_before" "$backup_after"
        ;;
    rollback)
        "$CADENCE_MCP_PYTHON" "$RECOVERY_HELPER" rollback "$stdout_file" \
            "$source_before" "$source_after" "$preserved_before" "$preserved_after" \
            "$backup_before" "$backup_after" "$target_before" "$target_after"
        ;;
esac
