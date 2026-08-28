#!/bin/bash

set -u
umask 077

. /home/buet/cds_work/.cadence_mcp/lib/runner-common.sh

WRITE_ROOT="$CADENCE_MCP_ROOT/write-validation"
POLICY="$CADENCE_MCP_ROOT/config/design-write-policy.json"
HELPER="$CADENCE_MCP_ROOT/py26/write_validation_json.py"
SCRIPT="$CADENCE_MCP_ROOT/write/design-write-validation.il"
VIRTUOSO_BIN=/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
SOURCE_VIEW=/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic
TARGET_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic
BACKUP_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic
PRESERVED_VIEW=/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic
AUDIT_LOG="$CADENCE_MCP_AUDIT_ROOT/write-events.jsonl"

[ "$#" -eq 2 ] || cadence_mcp_fail "invalid write validation invocation" 64
validation_id=$1
origin=$2
cadence_mcp_validate_job_id "$validation_id" || cadence_mcp_fail "invalid validation id" 64
case "$origin" in
    mcp) actor=cadence-mcp-bridge ;;
    operator) actor=$(id -un) ;;
    *) cadence_mcp_fail "invalid validation origin" 64 ;;
esac
[ -x "$VIRTUOSO_BIN" ] || cadence_mcp_fail "Virtuoso is unavailable" 69
[ -d "$SOURCE_VIEW" ] && [ ! -L "$SOURCE_VIEW" ] \
    || cadence_mcp_fail "fixed source cellview is unavailable" 69
[ -d "$PRESERVED_VIEW" ] && [ ! -L "$PRESERVED_VIEW" ] \
    || cadence_mcp_fail "preserved incomplete target is unavailable" 69
[ ! -e "$TARGET_VIEW" ] || cadence_mcp_fail "target cellview already exists" 65
[ ! -e "$BACKUP_VIEW" ] || cadence_mcp_fail "backup cellview already exists" 65
source_artifact=$(find "$SOURCE_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -name '*panic*' \) -print -quit)
[ -z "$source_artifact" ] \
    || cadence_mcp_fail "source cellview lock or recovery artifact is present" 65

mkdir -p "$WRITE_ROOT" "$CADENCE_MCP_AUDIT_ROOT" || cadence_mcp_fail "write layout failed" 73
chmod 700 "$WRITE_ROOT" "$CADENCE_MCP_AUDIT_ROOT"
validation_dir="$WRITE_ROOT/$validation_id"
[ ! -e "$validation_dir" ] || cadence_mcp_fail "validation id already exists" 65
mkdir -m 700 "$validation_dir" || cadence_mcp_fail "validation directory failed" 73

fingerprint_tree() {
    directory=$1
    (
        cd "$directory" || exit 1
        find . -type f -exec sha256sum '{}' \; | LC_ALL=C sort | sha256sum | cut -d ' ' -f 1
    )
}

source_before=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source baseline fingerprint failed" 70
preserved_before=$(fingerprint_tree "$PRESERVED_VIEW") \
    || cadence_mcp_fail "preserved target baseline fingerprint failed" 70
stdout_file="$validation_dir/skill.stdout"
stderr_file="$validation_dir/skill.stderr"
log_file="$validation_dir/skill.log"
(
    cd /home/buet/cds_work || exit 73
    timeout 90 "$VIRTUOSO_BIN" -nograph -nocdsinit -restore "$SCRIPT" -log "$log_file" \
        > "$stdout_file" 2> "$stderr_file"
)
skill_exit=$?
chmod 600 "$stdout_file" "$stderr_file" "$log_file" 2>/dev/null || true
[ "$skill_exit" -eq 0 ] || cadence_mcp_fail "fixed design write validation failed" 70
target_artifact=$(find "$TARGET_VIEW" "$BACKUP_VIEW" -maxdepth 1 \
    \( -name '*.cdslck*' -o -name 'sch.oa-' -o -name '*panic*' \) -print -quit)
[ -z "$target_artifact" ] \
    || cadence_mcp_fail "V2 cellview lock or recovery artifact remains" 70
source_after=$(fingerprint_tree "$SOURCE_VIEW") \
    || cadence_mcp_fail "source final fingerprint failed" 70
preserved_after=$(fingerprint_tree "$PRESERVED_VIEW") \
    || cadence_mcp_fail "preserved target final fingerprint failed" 70
manifest="$validation_dir/validation-manifest.json"
"$CADENCE_MCP_PYTHON" "$HELPER" "$POLICY" finalize \
    "$validation_id" "$stdout_file" "$source_before" "$source_after" \
    "$preserved_before" "$preserved_after" "$origin" "$actor" "$AUDIT_LOG" "$manifest"
