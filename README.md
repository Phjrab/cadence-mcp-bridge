# Cadence MCP Bridge

Private project for connecting Codex Desktop on Windows 11 to a legacy Cadence Virtuoso/Spectre/OCEAN environment in a CentOS 6.5 VMware VM through a restricted MCP server and SSH runner.

## Start here

1. Extract this starter bundle to a temporary folder such as Downloads. Do not extract it directly into `C:\work\cadence-mcp-bridge` because WP-00 uses that path as the clean clone destination.
2. Open the extracted starter folder in Codex Desktop.
3. Select **GPT-5.6 Terra / high** for WP-00.
4. Ask Codex:

```text
저장소의 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md를 전부 읽고, 첫 번째 미완료 워크패키지 하나만 실행하라. 최신 origin/main에서 해당 WP 전용 feature branch를 만들고, 수락 기준 검증, PROJECT_STATE.md 갱신, 커밋, feature branch push까지 완료한 뒤 필수 완료 보고서 형식으로 끝내라. main에 직접 push하거나 merge하지 말고 다음 WP도 시작하지 마라.
```

WP-00 may run `scripts/bootstrap-private-repo.ps1` to create the private repository and clean clone at `C:\work\cadence-mcp-bridge`. After the WP-00 feature branch is reviewed and integrated, open that cloned repository for WP-01 and later work.

The master prompt requires each run to finish with the next work package, recommended GPT-5.6 tier, reasoning effort, and exact next prompt.

Every WP uses a dedicated feature branch. Codex must not commit or push directly to `main`, and it must never force-push. After the completion report, Codex may merge a specific pull request only when the user explicitly authorizes that merge. The next WP starts only after the preceding branch is integrated into `main`.

## Verified target

- Windows 11, Codex Desktop, VMware Workstation Pro
- SSH alias: `cadence-vm`
- Remote: CentOS 6.5 i686, user `buet`
- Remote work root: `/home/buet/cds_work`
- Virtuoso: IC6.1.5.500.15
- Spectre: 12.1.0.347.isr3
- OCEAN available
- Passwordless SSH verified
- Headless Spectre smoke simulation verified with exit code 0

See `docs/VERIFIED_ENVIRONMENT.md` for the full evidence baseline.

## Windows development and stdio server

WP-01 targets Python 3.12 and uses `uv` for reproducible environments:

```powershell
uv sync --all-groups
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -m cadence_mcp_bridge --help
```

Run the MCP SDK v2 server over stdio with no command, or explicitly with `serve`:

```powershell
uv run python -m cadence_mcp_bridge
uv run python -m cadence_mcp_bridge serve
```

The server exposes only `cadence_health`, `cadence_submit_smoke`, `cadence_job_status`,
`cadence_job_log_tail`, `cadence_job_result`, and `cadence_cancel_job`. Register the reviewed
server with `.\scripts\install-codex-mcp.ps1`, then follow `docs/CODEX_DESKTOP.md` for restart,
`/mcp`, approval, and acceptance prompts. See `docs/ARCHITECTURE.md` for the current boundaries.

Run the reviewed MCP-to-Spectre health and smoke lifecycle verification with:

```powershell
.\scripts\verify-e2e.ps1
```

Run the WP-07 security gate and the non-destructive 30-day retention preview with:

```powershell
.\scripts\verify-security.ps1
.\scripts\cleanup-remote-jobs.ps1
```

The cleanup command is always a dry run. It has no delete mode and never accepts a path.
