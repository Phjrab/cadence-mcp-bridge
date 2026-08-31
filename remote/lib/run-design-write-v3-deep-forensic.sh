#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

VALIDATION_ID=0b9bf93c-11e9-416f-9e4a-69b1060fbd8e
SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic
BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic
POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
WRITE_HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
FORENSIC_HELPER="$CADENCE_MCP_ROOT/py26/v3_deep_forensic_json.py"
FORENSIC_SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v3-deep-forensic.il"
EVIDENCE_ROOT="$CADENCE_MCP_ROOT/write-validation-v3/$VALIDATION_ID"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 0 ] || cadence_mcp_fail "invalid V3 deep-forensic invocation" 64
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V3 deep forensics" 65
fi
"$CADENCE_MCP_PYTHON" "$WRITE_HELPER" "$POLICY" source-check \
    || cadence_mcp_fail "source master or artifact check failed" 65
for view in "$SOURCE_VIEW" "$TARGET_VIEW" "$BACKUP_VIEW"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed V3 deep-forensic cellview is unavailable" 69
done

blocking_artifact=$(find "$SOURCE_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "source artifact blocks V3 deep forensics" 65
blocking_artifact=$(find "$TARGET_VIEW" "$BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "V3 artifact blocks deep forensics" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source deep-forensic fingerprint failed" 70
target_before=$(fingerprint_tree "$TARGET_VIEW") \
    || cadence_mcp_fail "target deep-forensic fingerprint failed" 70
backup_before=$(fingerprint_tree "$BACKUP_VIEW") \
    || cadence_mcp_fail "backup deep-forensic fingerprint failed" 70

runtime="$EVIDENCE_ROOT/deep-forensic-v1"
[ ! -e "$runtime" ] || cadence_mcp_fail "V3 deep-forensic runtime already exists" 65
mkdir -m 700 "$runtime" || cadence_mcp_fail "V3 deep-forensic runtime creation failed" 73
stdout_file="$runtime/skill.stdout"
stderr_file="$runtime/skill.stderr"
log_file="$runtime/skill.log"
report_file="$runtime/v3-deep-forensic-report.json"
(
    cd /home/buet/cds_work || exit 73
    timeout 180 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$FORENSIC_SCRIPT" \
        -log "$log_file" > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V3 deep-forensic SKILL failed" 70

if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "Virtuoso remained active after V3 deep forensics" 70
fi
remaining_artifact=$(find "$SOURCE_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "source artifact remains after deep forensics" 70
remaining_artifact=$(find "$TARGET_VIEW" "$BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "V3 artifact remains after deep forensics" 70

source_after=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source post-forensic fingerprint failed" 70
target_after=$(fingerprint_tree "$TARGET_VIEW") \
    || cadence_mcp_fail "target post-forensic fingerprint failed" 70
backup_after=$(fingerprint_tree "$BACKUP_VIEW") \
    || cadence_mcp_fail "backup post-forensic fingerprint failed" 70

"$CADENCE_MCP_PYTHON" "$FORENSIC_HELPER" report "$stdout_file" "$report_file" \
    "$source_before" "$source_after" "$target_before" "$target_after" \
    "$backup_before" "$backup_after"
