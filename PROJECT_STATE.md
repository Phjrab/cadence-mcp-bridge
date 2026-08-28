# Project State

```yaml
project: cadence-mcp-bridge
repository: Phjrab/cadence-mcp-bridge
visibility: private
current_wp: WP-09
current_status: blocked
last_completed_wp: WP-08
next_wp: WP-09
current_feature_branch: wp/WP-09-ade-testbench-profiles
base_main_commit: 9a109c098c2efd505aaa42761a1acc3a85b1104a
last_commit: 71ab3dfa37d5c7c5c503d17352052b3be5f45289
last_push: 2026-08-28T13:09:35.8521991+09:00
awaiting_user_merge: true
remote_runner_deployed: true
codex_mcp_registered: true
last_e2e_result: pass
user_action_required: Provide the actual ADE profile choices listed in docs/USER_INPUTS_REQUIRED.md, then continue WP-09 on the existing feature branch.
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
