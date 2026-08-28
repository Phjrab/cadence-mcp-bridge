# Project State

```yaml
project: cadence-mcp-bridge
repository: Phjrab/cadence-mcp-bridge
visibility: private
current_wp: WP-11
current_status: blocked
last_completed_wp: WP-10
next_wp: WP-11
current_feature_branch: wp/WP-11-controlled-design-writes-release
base_main_commit: 28974d6557a8db8080cd7c0dee9017c9fd65fd60
last_commit: ada4d549b78d7b4b80c3a0e5292bb249eedea1b9
last_push: 2026-08-28T19:50:00.1038356+09:00
awaiting_user_merge: false
remote_runner_deployed: true
codex_mcp_registered: true
last_e2e_result: fail
user_action_required: Validation `e55c7e81-cf20-4d5e-b2d9-67dae0ddcd1b` timed out after the approved apply stage but before apply verification and rollback. Both V2 target and backup now exist, so the approved no-reuse/no-overwrite contract blocks another V2 run. Normally close active buet Virtuoso PID 24345 without force termination. Then explicitly approve either a fixed read-only forensic inspection plus narrowly scoped V2 rollback/recovery, or new clean destination and backup names for another validation. Do not delete, overwrite, or reuse the V2 artifacts under the current approval. No v1 tag or release is permitted.
```

## Progress log

- 2026-08-28: Initial execution plan prepared. WP-00 is pending.
- 2026-08-28: WP-00 bootstrap committed on wp/WP-00-bootstrap; awaiting user review and merge.
- 2026-08-28: User explicitly authorized Codex to merge PR #1; contract updated to permit only explicitly authorized PR merges.
- 2026-08-28: WP-01 Windows scaffold and typed contracts passed all acceptance checks; awaiting review and merge authorization.
- 2026-08-28: User explicitly authorized PR #2; WP-01 merged into main.
- 2026-08-28: WP-02 restricted runner deployed under the approved root; smoke and cancellation acceptance passed.
- 2026-08-28: User explicitly authorized PR #3; WP-02 merged into main as 581450b.
- 2026-08-28: WP-03 allowlisted Windows OpenSSH backend passed unit, static, and real cadence-vm health integration checks.
- 2026-08-28: User explicitly authorized PR #4; WP-03 merged into main as 9c862c3.
- 2026-08-28: WP-04 MCP SDK v2 stdio server passed schema, mock, stdout, static, and real cadence_health integration checks.
- 2026-08-28: User explicitly authorized PR #5; WP-04 merged into main as 6ba2c66.
- 2026-08-28: WP-05 actual MCP-to-Spectre lifecycle, bounded polling, recovery, storage, and cancellation isolation checks passed.
- 2026-08-28: User explicitly authorized PR #6; WP-05 merged into main as 18bb372.
- 2026-08-28: WP-06 idempotent Codex registration, approval policy, fresh-host health, and smoke lifecycle checks passed; Desktop restart/UI confirmation remains an operator action.
- 2026-08-28: User explicitly authorized PR #7; WP-06 merged into main as 714d4ca.
- 2026-08-28: WP-07 isolation, audit, bounded output, dry-run retention, recovery, concurrency, secret, dependency, and real cadence-vm acceptance checks passed; awaiting review and merge authorization.
- 2026-08-28: User explicitly authorized PR #8; WP-07 merged into main as 2786fbc.
- 2026-08-28: WP-08 fixed OCEAN/SKILL headless checks, allowlisted metadata-only discovery, PDK denial, and design/lock fingerprint acceptance passed; awaiting review and merge authorization.
- 2026-08-28: User explicitly authorized PR #9; WP-08 merged into main as 9a109c0.
- 2026-08-28: WP-09 fixture profile registry, typed range/corner validation, manifest, runner 0.6.0, and real MCP lifecycle checks passed; actual ADE profile remains blocked on project-owned testbench, state, variable, corner, and output choices.
- 2026-08-28: WP-09 resume approval received; the remote feature branch was synchronized and all local/security/real-integration checks passed again, but no ADE testbench, PDK, variable, corner, or output choices were supplied, so the actual profile remains blocked and is not ready for merge.
- 2026-08-28: User supplied and approved the Differential_Amplifier_TB2 ADE L state1 profile; runner 0.7.0 executed its fixed gpdk090 v4.6 NN transient profile successfully with 0 errors, two specifically allowlisted CMI-2477 warnings, unchanged source/state/lock fingerprints, 106 local tests, 18 security tests, eight real integrations, and a clean dependency audit.
- 2026-08-28: User explicitly authorized PR #10; WP-09 merged into main as 5b22da7.
- 2026-08-28: WP-10 added the closed adc-synthetic-v1 version 1 measurement contract, deterministic Windows-Python metrics and manifests, twenty-tool MCP schema, explicit actual-ADC input boundary, 117 local tests, 18 security tests, eight real integrations, and a clean dependency audit; awaiting review and merge authorization.
- 2026-08-28: User explicitly authorized PR #11; WP-10 merged into main as 28974d6.
- 2026-08-28: WP-11 read-only discovery found only MyDesignLib and MyFirstDesign, with no dedicated approved work library or mutation. A fail-closed local write readiness gate, package install/uninstall verifier, release checklist, and draft notes passed 131 local tests, 18 security tests, eight real integrations, and dependency audit. No write tool, remote mutation, design change, v1 tag, or release was created; WP-11 remains blocked on the required user-owned write contract and explicit mutation approval.
- 2026-08-28: User supplied and approved MCP_WorkLib, the exact Differential_Amplifier_TB2 copy, and the sole mcpMutationTest=validated-v1 mutation with real apply/rollback. Runner 0.8.0 and twenty-two typed MCP tools were implemented. The real run created the approved destination copy but stopped before dry-run completion because IC6.1.5 lacks dbFindPropByName; the property was not applied and backup/rollback did not run. The corrected fixed script is deployed but the existing-target rule blocks retry. Local 137 tests, 18 security tests, eight non-write real integrations, Ruff, mypy, package lifecycle, and dependency audit pass; write acceptance failed, so no v1 tag or release exists.
- 2026-08-28: User approved a clean V2 destination and backup while requiring the incomplete V1 target and recovery artifacts to remain untouched. Runner 0.9.0 adds the V2 canonical plan, backup-based restore, logical baseline fingerprints, preserved-V1 fingerprints, IC6.1.5-compatible property access, and source/V2 lock and recovery-artifact gates. The V2 names are absent and a fixed read-only SKILL API preflight passed, but the final gate found active source locks `/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic/sch.oa.cdslck` and `.RHEL30.cadence.25425`, owned by running buet Virtuoso PID 25425. Per the user's policy, no V2 copy or mutation was attempted. Local 140 tests, 18 security tests, eight real integrations, Ruff, mypy, package lifecycle, and dependency audit pass; WP-11 remains blocked and no v1 tag or release exists.
- 2026-08-28: After the user ended Virtuoso PID 25425 normally, a read-only recheck found no running Virtuoso process and no PID 25425 process, but the source still contains `/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic/sch.oa.cdslck` and `sch.oa.cdslck.RHEL30.cadence.25425` (owner `buet:buet`, timestamp `2026-08-28 10:54:52.804994291 +0600`) plus the recovery-like `sch.oa-` artifact (owner `buet:buet`, timestamp `2026-08-28 16:14:37.276978537 +0600`). The V2 destination and V2 backup remain absent, the V1 target remains preserved, and the canonical plan reports `ready=false` with `source_artifact_present=true`. No copy, dry-run, backup, apply, rollback, tag, or release was attempted; WP-11 remains blocked pending Cadence-supported artifact resolution.
- 2026-08-28: The user completed Cadence-supported lock recovery by reopening and closing the source cellView without edits and normally exiting Virtuoso. A read-only recheck confirmed that no Virtuoso process or `.cdslck`/CLS artifact remains. However, `/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic/sch.oa-` remains a 42,508-byte regular data file owned by `buet:buet`, timestamped `2026-08-28 16:14:37.276978537 +0600`; its meaning cannot be safely established. The V2 destination and backup remain absent and the plan remains fail-closed with `source_artifact_present=true`. Per the explicit approval boundary, the file was not deleted or modified and no V2 validation or release action was attempted.
- 2026-08-28: The user established through Cadence/OpenAccess that `master.tag` authoritatively selects `sch.oa`, the preserved source `sch.oa-` is not an active lock, and a read-only source open reports 35 instances, 14 nets, and eight terminals. The fixed gate was updated to require that authoritative master and exact topology while preserving and fingerprinting `sch.oa-`; 141 local tests, 18 security tests, Ruff, mypy, secret scanning, and dependency audit pass. Real validation `e55c7e81-cf20-4d5e-b2d9-67dae0ddcd1b` passed source verify, V2 copy, 35/14/8 baseline, non-mutating dry-run, unchanged verification, backup, and the approved one-property apply marker, then hit the fixed 90-second timeout before apply verification or rollback. The V2 target and backup now exist, no validation manifest or audit records were produced, and active buet Virtuoso PID 24345 was observed. No retry, deletion, overwrite, tag, or release was attempted; WP-11 remains blocked on a new explicit recovery or clean-destination decision.
