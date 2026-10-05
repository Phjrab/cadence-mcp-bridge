# AGENTS.md

## Project authority

Before doing any work, read these files in full:

1. `CODEX_MASTER_PROMPT.md`
2. `PROJECT_STATE.md`
3. `docs/CURRENT_PHASE_PLAN.md`
4. `docs/VERIFIED_ENVIRONMENT.md`
5. `docs/SECURITY.md`
6. `docs/agent_plan/WORK_ID_MAP.md` when the active WP cites an `ICF-*` task or package capability
7. Only the sections of `docs/AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md` or
   `docs/agent_plan/` that the current WP explicitly requires

`CODEX_MASTER_PROMPT.md` is the authoritative execution contract.

## Active phase delegation (2026-09-29)

The user's explicit AUTO-PHASE-01 instruction supersedes the project-level one-WP
STOP, per-PR merge approval, and per-read approval rules below for operations inside
`docs/policy/PHASE_CAMPAIGN_V1.json` and the scope in
`docs/policy/PHASE_AUTONOMY_V1.md`. Read the migration record there before using the
new operator path. The rules below remain historical or apply outside this delegation.
The user's later explicit removal of the eight-hour elapsed ceiling is bound by
`docs/policy/PHASE_ELAPSED_LIMIT_V2.json`; all other cumulative limits remain active.
The user's 2026-10-04 instruction raises the cumulative Spectre ceiling to 500
through `docs/policy/PHASE_SPECTRE_LIMIT_V3.json` and the native-v2 adapter.
Consumed attempts and result reservations are retained. The later explicit 2026-10-05 instruction raises the active result ceiling to
10 GiB through `PHASE_RESULT_LIMIT_V4.json`, preserving consumed reservations.
Historical versioned limits remain immutable. The other
resource limits and all prior correction histories remain binding.
The old single-use authorization paths and records are unchanged. A new operation
must pass its own policy, identity, integrity, budget, and replay checks; a policy
file alone is not proof of user delegation. GitHub protections and platform access
controls still apply.

Within the delegated scope, finish a phase, report its evidence, then continue the
next prepared phase without another project-level approval. Create and merge only
reviewed feature PRs, never push directly to main or bypass required checks/reviews.
Do not create a PR only to record that a previous PR merged. PR #57 and WP-15/WP-16
are complete. WP-14 is the current circuit task.

For questions, blockers, and completion reports, also read
`docs/interaction/GOALS_FACTS_AND_APPROVALS.md`. It separates user design choices,
facts the agent must investigate, and execution scope. The current user delegation
governs its in-scope access; the historical approval gates govern legacy operations.

Do not read or execute the full long-term roadmap as a single run instruction. Treat
`docs/CURRENT_PHASE_PLAN.md` as the bounded phase plan and consult only the roadmap sections
needed to understand or verify the active WP.

The imported `docs/agent_plan/` package is a planning and contract reference, not a blanket
execution approval. Its templates, archived material, example values, future work packages, and
recovered approvals remain inactive unless the current root contract and a specific active WP make
them applicable. When rules conflict, preserve the stricter existing approval, security, Git, and
evidence-protection boundary and record the decision rather than weakening it.

## Legacy one work package per run (superseded in AUTO-PHASE-01)

- Execute only the requested work package, or the first incomplete WP in `PROJECT_STATE.md`.
- Do not automatically start the next WP.
- Finish with the exact completion report required by the master prompt.
- Always include the recommended model, effort, and exact start prompt for the next run.

## Legacy Git discipline (superseded in AUTO-PHASE-01 where noted)

- Inspect status and remote before edits.
- Never discard unrelated changes.
- Run the WP acceptance checks before commit.
- Update `PROJECT_STATE.md`.
- Create or continue only the current WP feature branch from the latest approved `origin/main`.
- Commit with a conventional message and push that feature branch.
- Never commit or push directly to `main`.
- Never push directly to `main` and never force push.
- Merge a feature branch only when the user explicitly authorizes that specific branch or pull request after its completion report.
- Stop immediately after verifying the feature branch push unless that explicit merge authorization has been given.
- Never claim a push succeeded without verifying it.

## Security

Never add a generic shell, SSH command, SKILL eval, or OCEAN script execution tool. Never commit SSH keys, credentials, license values, PDK content, proprietary netlists, raw/PSF data, or unrestricted logs.

The CentOS system Python and OS must not be upgraded or modified. Remote writes are limited to `/home/buet/cds_work/.cadence_mcp` until explicitly authorized in WP-11.
