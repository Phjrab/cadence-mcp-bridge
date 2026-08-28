# AGENTS.md

## Project authority

Before doing any work, read these files in full:

1. `CODEX_MASTER_PROMPT.md`
2. `PROJECT_STATE.md`
3. `docs/VERIFIED_ENVIRONMENT.md`
4. `docs/SECURITY.md`

`CODEX_MASTER_PROMPT.md` is the authoritative execution contract.

## One work package per run

- Execute only the requested work package, or the first incomplete WP in `PROJECT_STATE.md`.
- Do not automatically start the next WP.
- Finish with the exact completion report required by the master prompt.
- Always include the recommended model, effort, and exact start prompt for the next run.

## Git discipline

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
