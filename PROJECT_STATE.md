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
last_commit: ea6025e354b93b02e341361dab5e5a8a77ea5d81
last_push: 2026-08-28T18:50:11.6455223+09:00
awaiting_user_merge: false
remote_runner_deployed: true
codex_mcp_registered: true
last_e2e_result: fail
user_action_required: Close or safely finish the Virtuoso session running as buet PID 25425 that owns the source schematic OA lock, and allow Cadence to remove its lock files normally. Do not delete or force-release the lock. Then resume WP-11 on the same branch so lock absence can be verified before the approved V2 validation. No v1 tag or release is permitted before a clean sequence passes.
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
