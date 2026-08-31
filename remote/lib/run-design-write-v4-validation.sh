#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

PLAN="$CADENCE_MCP_ROOT/config/design-write-v4-plan.json"
HELPER="$CADENCE_MCP_ROOT/py26/v4_validation_json.py"
SOURCE_HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
SOURCE_POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
SCRIPT="$CADENCE_MCP_ROOT/write/design-write-v4-validation.il"
VALIDATION_ROOT="$CADENCE_MCP_ROOT/write-validation-v4"
AUDIT_LOG="$CADENCE_MCP_AUDIT_ROOT/v4-validation-events.jsonl"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
V1_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic
V2_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic
V2_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic
V3_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic
V3_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic
V4_TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4/schematic
V4_BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP/schematic
PDK_VIEW=/home/buet/cadence/gpdk090_v4.6/libs.oa22/gpdk090

[ "$#" -eq 2 ] || cadence_mcp_fail "invalid V4 validation invocation" 64
run_id=$1
origin=$2
cadence_mcp_validate_job_id "$run_id" || cadence_mcp_fail "invalid V4 run id" 64
[ "$origin" = operator ] || cadence_mcp_fail "invalid V4 origin" 64
actor=$(id -un)

[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "active Virtuoso process blocks V4 validation" 65
fi
"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" plan-check \
    || cadence_mcp_fail "approved V4 plan verification failed" 65
"$CADENCE_MCP_PYTHON" "$SOURCE_HELPER" "$SOURCE_POLICY" source-check \
    || cadence_mcp_fail "source master or artifact check failed" 65

for view in "$SOURCE_VIEW" "$V1_VIEW" "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" "$PDK_VIEW"; do
    [ -d "$view" ] && [ ! -L "$view" ] \
        || cadence_mcp_fail "fixed protected V4 input is unavailable" 69
done
[ ! -e "$V4_TARGET_VIEW" ] || cadence_mcp_fail "V4 target already exists" 65
[ ! -e "$V4_BACKUP_VIEW" ] || cadence_mcp_fail "V4 backup already exists" 65

blocking=$(find "$SOURCE_VIEW" "$V1_VIEW" "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) -print -quit)
[ -z "$blocking" ] || cadence_mcp_fail "blocking V4 artifact is present" 65
blocking=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" "$V3_TARGET_VIEW" \
    "$V3_BACKUP_VIEW" -maxdepth 1 -name 'sch.oa-' -print -quit)
[ -z "$blocking" ] || cadence_mcp_fail "protected V2 or V3 auxiliary artifact is present" 65

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") || cadence_mcp_fail "source fingerprint failed" 70
v1_before=$(fingerprint_tree "$V1_VIEW") || cadence_mcp_fail "V1 fingerprint failed" 70
v2_target_before=$(fingerprint_tree "$V2_TARGET_VIEW") || cadence_mcp_fail "V2 target fingerprint failed" 70
v2_backup_before=$(fingerprint_tree "$V2_BACKUP_VIEW") || cadence_mcp_fail "V2 backup fingerprint failed" 70
v3_target_before=$(fingerprint_tree "$V3_TARGET_VIEW") || cadence_mcp_fail "V3 target fingerprint failed" 70
v3_backup_before=$(fingerprint_tree "$V3_BACKUP_VIEW") || cadence_mcp_fail "V3 backup fingerprint failed" 70
pdk_before=$(fingerprint_tree "$PDK_VIEW") || cadence_mcp_fail "PDK fingerprint failed" 70

mkdir -p "$VALIDATION_ROOT" "$CADENCE_MCP_AUDIT_ROOT" \
    || cadence_mcp_fail "V4 validation layout failed" 73
chmod 700 "$VALIDATION_ROOT" "$CADENCE_MCP_AUDIT_ROOT" \
    || cadence_mcp_fail "V4 validation layout permission failed" 73
runtime="$VALIDATION_ROOT/$run_id"
[ ! -e "$runtime" ] || cadence_mcp_fail "V4 validation run already exists" 65
mkdir -m 700 "$runtime" || cadence_mcp_fail "V4 validation runtime creation failed" 73
stdout_file="$runtime/skill.stdout"
stderr_file="$runtime/skill.stderr"
log_file="$runtime/skill.log"
manifest="$runtime/validation-manifest.json"
(
    cd /home/buet/cds_work || exit 73
    timeout 300 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" -log "$log_file" \
        > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed V4 validation SKILL failed" 70

if ps -ef | grep '[v]irtuoso' >/dev/null 2>&1; then
    cadence_mcp_fail "Virtuoso remained active after V4 validation" 70
fi
[ -d "$V4_TARGET_VIEW" ] && [ ! -L "$V4_TARGET_VIEW" ] \
    || cadence_mcp_fail "V4 target was not created" 70
[ -d "$V4_BACKUP_VIEW" ] && [ ! -L "$V4_BACKUP_VIEW" ] \
    || cadence_mcp_fail "V4 backup was not created" 70
remaining=$(find "$SOURCE_VIEW" "$V1_VIEW" "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" \
    "$V3_TARGET_VIEW" "$V3_BACKUP_VIEW" "$V4_TARGET_VIEW" "$V4_BACKUP_VIEW" \
    -maxdepth 1 \( -name '*.cdslck*' -o -iname '*panic*' -o -iname '*recover*' \) \
    -print -quit)
[ -z "$remaining" ] || cadence_mcp_fail "blocking artifact remains after V4 validation" 70
remaining=$(find "$V2_TARGET_VIEW" "$V2_BACKUP_VIEW" "$V3_TARGET_VIEW" \
    "$V3_BACKUP_VIEW" "$V4_TARGET_VIEW" "$V4_BACKUP_VIEW" -maxdepth 1 \
    -name 'sch.oa-' -print -quit)
[ -z "$remaining" ] || cadence_mcp_fail "unexpected auxiliary artifact remains after V4 validation" 70

source_after=$(fingerprint_tree "$SOURCE_VIEW") || cadence_mcp_fail "source final fingerprint failed" 70
v1_after=$(fingerprint_tree "$V1_VIEW") || cadence_mcp_fail "V1 final fingerprint failed" 70
v2_target_after=$(fingerprint_tree "$V2_TARGET_VIEW") || cadence_mcp_fail "V2 target final fingerprint failed" 70
v2_backup_after=$(fingerprint_tree "$V2_BACKUP_VIEW") || cadence_mcp_fail "V2 backup final fingerprint failed" 70
v3_target_after=$(fingerprint_tree "$V3_TARGET_VIEW") || cadence_mcp_fail "V3 target final fingerprint failed" 70
v3_backup_after=$(fingerprint_tree "$V3_BACKUP_VIEW") || cadence_mcp_fail "V3 backup final fingerprint failed" 70
pdk_after=$(fingerprint_tree "$PDK_VIEW") || cadence_mcp_fail "PDK final fingerprint failed" 70
target_final=$(fingerprint_tree "$V4_TARGET_VIEW") || cadence_mcp_fail "V4 target final fingerprint failed" 70
backup_final=$(fingerprint_tree "$V4_BACKUP_VIEW") || cadence_mcp_fail "V4 backup final fingerprint failed" 70

"$CADENCE_MCP_PYTHON" "$HELPER" "$PLAN" finalize "$run_id" "$stdout_file" \
    "$source_before" "$source_after" "$v1_before" "$v1_after" \
    "$v2_target_before" "$v2_target_after" "$v2_backup_before" "$v2_backup_after" \
    "$v3_target_before" "$v3_target_after" "$v3_backup_before" "$v3_backup_after" \
    "$pdk_before" "$pdk_after" "$target_final" "$backup_final" \
    "$origin" "$actor" "$AUDIT_LOG" "$manifest"
