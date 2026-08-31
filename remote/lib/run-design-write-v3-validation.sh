#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

PLAN="$CADENCE_MCP_ROOT/config/design-write-v3-plan.json"
HELPER="$CADENCE_MCP_ROOT/py26/v3_validation_json.py"
SOURCE_HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
SOURCE_POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v3-validation.il"
VALIDATION_ROOT="$CADENCE_MCP_ROOT/write-validation-v3"
AUDIT_LOG="$CADENCE_MCP_AUDIT_ROOT/write-events.jsonl"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
V1_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic
V2_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic
V2_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic
V3_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic
V3_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic
PDK_VIEW=/home/buet/cadence/gpdk090_v4.6/libs.oa22/gpdk090

[ "$#" -eq 2 ] || cadence_mcp_fail "invalid V3 validation invocation" 64
validation_id=$1
origin=$2
cadence_mcp_validate_job_id "$validation_id" || cadence_mcp_fail "invalid V3 validation id" 64
case "$origin" in
    mcp) actor=cadence-mcp-bridge ;;
    operator) actor=$(id -un) ;;
    *) cadence_mcp_fail "invalid V3 validation origin" 64 ;;
esac

[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V3 validation" 65
fi
"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" plan-check \
    || cadence_mcp_fail "approved V3 plan verification failed" 65
"$CADENCE_MCP_PYTHON" "$SOURCE_HELPER" "$SOURCE_POLICY" source-check \
    || cadence_mcp_fail "source master or artifact check failed" 65

for view in "$SOURCE_VIEW" "$V1_VIEW" "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" "$PDK_VIEW"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed protected V3 input is unavailable" 69
done
[ -f "$V1_VIEW/master.tag" ] && [ ! -L "$V1_VIEW/master.tag" ] \
    && [ -f "$V1_VIEW/sch.oa" ] && [ ! -L "$V1_VIEW/sch.oa" ] \
    || cadence_mcp_fail "preserved V1 authoritative master is unavailable" 65
v1_master_references=$(grep -v '^[[:space:]]*--' "$V1_VIEW/master.tag" \
    | sed '/^[[:space:]]*$/d')
[ "$v1_master_references" = "sch.oa" ] \
    || cadence_mcp_fail "preserved V1 master.tag is not authoritative" 65
[ ! -e "$V3_TARGET_VIEW" ] || cadence_mcp_fail "V3 target already exists" 65
[ ! -e "$V3_BACKUP_VIEW" ] || cadence_mcp_fail "V3 backup already exists" 65

blocking_artifact=$(find "$V1_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "protected V1 artifact blocks V3 validation" 65
blocking_artifact=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$blocking_artifact" ] || cadence_mcp_fail "protected V2 artifact blocks V3 validation" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source V3 baseline fingerprint failed" 70
v1_before=$(fingerprint_tree "$V1_VIEW") \
    || cadence_mcp_fail "V1 V3 baseline fingerprint failed" 70
v2_target_before=$(fingerprint_tree "$V2_TARGET_VIEW") \
    || cadence_mcp_fail "V2 target V3 baseline fingerprint failed" 70
v2_backup_before=$(fingerprint_tree "$V2_BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup V3 baseline fingerprint failed" 70
pdk_before=$(fingerprint_tree "$PDK_VIEW") \
    || cadence_mcp_fail "PDK V3 baseline fingerprint failed" 70

mkdir -p "$VALIDATION_ROOT" "$CADENCE_MCP_AUDIT_ROOT" \
    || cadence_mcp_fail "V3 validation layout failed" 73
chmod 700 "$VALIDATION_ROOT" "$CADENCE_MCP_AUDIT_ROOT"
validation_dir="$VALIDATION_ROOT/$validation_id"
[ ! -e "$validation_dir" ] || cadence_mcp_fail "V3 validation id already exists" 65
mkdir -m 700 "$validation_dir" || cadence_mcp_fail "V3 validation directory failed" 73
stdout_file="$validation_dir/skill.stdout"
stderr_file="$validation_dir/skill.stderr"
log_file="$validation_dir/skill.log"
(
    cd /home/buet/cds_work || exit 73
    timeout 300 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" -log "$log_file" \
        > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V3 validation SKILL failed" 70

[ -d "$V3_TARGET_VIEW" ] && [ ! -L "$V3_TARGET_VIEW" ] \
    || cadence_mcp_fail "V3 target was not created" 70
[ -d "$V3_BACKUP_VIEW" ] && [ ! -L "$V3_BACKUP_VIEW" ] \
    || cadence_mcp_fail "V3 backup was not created" 70
remaining_artifact=$(find "$V1_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "protected V1 artifact remains after V3 validation" 70
remaining_artifact=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining_artifact" ] || cadence_mcp_fail "cellview artifact remains after V3 validation" 70
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "Virtuoso remained active after V3 validation" 70
fi

source_after=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source V3 final fingerprint failed" 70
v1_after=$(fingerprint_tree "$V1_VIEW") \
    || cadence_mcp_fail "V1 V3 final fingerprint failed" 70
v2_target_after=$(fingerprint_tree "$V2_TARGET_VIEW") \
    || cadence_mcp_fail "V2 target V3 final fingerprint failed" 70
v2_backup_after=$(fingerprint_tree "$V2_BACKUP_VIEW") \
    || cadence_mcp_fail "V2 backup V3 final fingerprint failed" 70
pdk_after=$(fingerprint_tree "$PDK_VIEW") \
    || cadence_mcp_fail "PDK V3 final fingerprint failed" 70
target_final=$(fingerprint_tree "$V3_TARGET_VIEW") \
    || cadence_mcp_fail "V3 target final fingerprint failed" 70
backup_final=$(fingerprint_tree "$V3_BACKUP_VIEW") \
    || cadence_mcp_fail "V3 backup final fingerprint failed" 70

manifest="$validation_dir/validation-manifest.json"
"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" finalize \
    "$validation_id" "$stdout_file" \
    "$source_before" "$source_after" "$v1_before" "$v1_after" \
    "$v2_target_before" "$v2_target_after" "$v2_backup_before" "$v2_backup_after" \
    "$pdk_before" "$pdk_after" "$target_final" "$backup_final" \
    "$origin" "$actor" "$AUDIT_LOG" "$manifest"
