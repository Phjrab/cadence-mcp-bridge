#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

VALIDATION_ID=0b9bf93c-11e9-416f-9e4a-69b1060fbd8e
SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
V1_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic
V2_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic
V2_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic
V3_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic
V3_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic
PDK_VIEW=/home/buet/cadence/gpdk090_v4.6/libs.oa22/gpdk090
POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
WRITE_HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
FORENSIC_HELPER="$CADENCE_MCP_ROOT/py26/v3_forensic_json.py"
FORENSIC_SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v3-property-diff.il"
EVIDENCE_ROOT="$CADENCE_MCP_ROOT/write-validation-v3/$VALIDATION_ID"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso

[ "$#" -eq 0 ] || cadence_mcp_fail "invalid V3 forensic invocation" 64
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V3 forensic inspection" 65
fi
"$CADENCE_MCP_PYTHON" "$WRITE_HELPER" "$POLICY" source-check \
    || cadence_mcp_fail "source master or artifact check failed" 65
for view in "$SOURCE_VIEW" "$V1_VIEW" "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" "$PDK_VIEW"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed V3 forensic input is unavailable" 69
done
[ -f "$V1_VIEW/master.tag" ] && [ ! -L "$V1_VIEW/master.tag" ] \
    && [ -f "$V1_VIEW/sch.oa" ] && [ ! -L "$V1_VIEW/sch.oa" ] \
    || cadence_mcp_fail "preserved V1 authoritative master is unavailable" 65
v1_master_references=$(grep -v '^[[:space:]]*--' "$V1_VIEW/master.tag" \
    | sed '/^[[:space:]]*$/d')
[ "$v1_master_references" = "sch.oa" ] \
    || cadence_mcp_fail "preserved V1 master.tag is not authoritative" 65

blocking_artifact=$(find "$V1_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "protected V1 artifact blocks V3 forensics" 65
blocking_artifact=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "protected cellview artifact blocks V3 forensics" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source V3 forensic fingerprint failed" 70
v1_before=$(fingerprint_tree "$V1_VIEW") \
    || cadence_mcp_fail "V1 V3 forensic fingerprint failed" 70
v2_target_before=$(fingerprint_tree "$V2_TARGET_VIEW") \
    || cadence_mcp_fail "V2 target V3 forensic fingerprint failed" 70
v2_backup_before=$(fingerprint_tree "$V2_BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup V3 forensic fingerprint failed" 70
v3_target_before=$(fingerprint_tree "$V3_TARGET_VIEW") \
    || cadence_mcp_fail "V3 target forensic fingerprint failed" 70
v3_backup_before=$(fingerprint_tree "$V3_BACKUP_VIEW") \
    || cadence_mcp_fail "V3 backup forensic fingerprint failed" 70
pdk_before=$(fingerprint_tree "$PDK_VIEW") \
    || cadence_mcp_fail "PDK V3 forensic fingerprint failed" 70

runtime="$EVIDENCE_ROOT/forensic-v1"
[ ! -e "$runtime" ] || cadence_mcp_fail "V3 forensic runtime already exists" 65
mkdir -m 700 "$runtime" || cadence_mcp_fail "V3 forensic runtime creation failed" 73
stdout_file="$runtime/skill.stdout"
stderr_file="$runtime/skill.stderr"
log_file="$runtime/skill.log"
(
    cd /home/buet/cds_work || exit 73
    timeout 180 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$FORENSIC_SCRIPT" \
        -log "$log_file" > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V3 forensic SKILL failed" 70

if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "Virtuoso remained active after V3 forensic inspection" 70
fi
remaining_artifact=$(find "$V1_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "protected V1 artifact remains after V3 forensics" 70
remaining_artifact=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] \
    || cadence_mcp_fail "cellview artifact remains after V3 forensics" 70

source_after=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source post-forensic fingerprint failed" 70
v1_after=$(fingerprint_tree "$V1_VIEW") \
    || cadence_mcp_fail "V1 post-forensic fingerprint failed" 70
v2_target_after=$(fingerprint_tree "$V2_TARGET_VIEW") \
    || cadence_mcp_fail "V2 target post-forensic fingerprint failed" 70
v2_backup_after=$(fingerprint_tree "$V2_BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup post-forensic fingerprint failed" 70
v3_target_after=$(fingerprint_tree "$V3_TARGET_VIEW") \
    || cadence_mcp_fail "V3 target post-forensic fingerprint failed" 70
v3_backup_after=$(fingerprint_tree "$V3_BACKUP_VIEW") \
    || cadence_mcp_fail "V3 backup post-forensic fingerprint failed" 70
pdk_after=$(fingerprint_tree "$PDK_VIEW") \
    || cadence_mcp_fail "PDK post-forensic fingerprint failed" 70

"$CADENCE_MCP_PYTHON" "$FORENSIC_HELPER" property-diff "$stdout_file" \
    "$source_before" "$source_after" "$v1_before" "$v1_after" \
    "$v2_target_before" "$v2_target_after" "$v2_backup_before" "$v2_backup_after" \
    "$v3_target_before" "$v3_target_after" "$v3_backup_before" "$v3_backup_after" \
    "$pdk_before" "$pdk_after"
