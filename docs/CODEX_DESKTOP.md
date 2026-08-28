# Codex Desktop Registration

## Install or update

From the repository root in Windows PowerShell:

```powershell
.\scripts\install-codex-mcp.ps1 -WhatIf
.\scripts\install-codex-mcp.ps1 -Confirm
```

The script resolves the repository and virtual-environment Python to absolute paths. Before any
change it backs up `%USERPROFILE%\.codex\config.toml`, then atomically writes one
`cadence-mcp-bridge` entry. Re-running the script with the same paths changes nothing and creates
no duplicate or backup.

The registration starts the stdio server with the absolute Python executable and
`-m cadence_mcp_bridge`. Startup timeout is 20 seconds and each individual tool call may take up
to 180 seconds, which covers the bridge's 120-second SSH operation limit. The full smoke workflow
still uses the separate five-minute bounded polling deadline.

`default_tools_approval_mode = "writes"` leaves health, status, log tail, result, discovery,
profile-list/profile-detail, and measurement tools read-only. Submission and cancellation have explicit
`approval_mode = "prompt"`; approve them only when the displayed request matches the intended
smoke job.

## Restart and inspect

1. Restart Codex Desktop after registration.
2. In a new task, enter `/mcp` and confirm `cadence-mcp-bridge` is enabled and connected.
3. Confirm exactly these twenty tools are visible:
   `cadence_health`, `cadence_submit_smoke`, `cadence_job_status`,
   `cadence_job_log_tail`, `cadence_job_result`, `cadence_cancel_job`,
   `cadence_list_libraries`, `cadence_list_cells`, and `cadence_inspect_cellview`.
   Also confirm `cadence_list_profiles`, `cadence_get_profile`, and `cadence_submit_profile`.
   Finally confirm `cadence_get_measurement_contract`, `cadence_measure_dc_power`,
   `cadence_measure_offset`, `cadence_measure_settling`, `cadence_measure_fft_metrics`,
   `cadence_measure_linearity`, `cadence_compare_corner_results`, and
   `cadence_summarize_monte_carlo`.
4. Confirm there is no raw shell, raw SSH, arbitrary file, SKILL eval, or OCEAN eval tool.

The Codex Desktop app, Codex CLI, and IDE extension share the same host MCP configuration. The
official configuration lives in `%USERPROFILE%\.codex\config.toml` on Windows.

Official references:

- [Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference.md)

## Acceptance prompts

Read-only health check:

```text
Cadence MCP 연결 상태를 확인해줘. 라이선스 변수의 실제 값은 출력하지 마.
```

Smoke lifecycle; approve the submission prompt, then let Codex poll with read-only tools:

```text
Spectre smoke test를 제출하고 완료될 때까지 상태를 확인한 뒤 결과를 요약해줘. raw/PSF 데이터나 라이선스 값은 출력하지 마.
```

Cancellation isolation; approve both submission and cancellation only for the returned job ID:

```text
Spectre smoke test 하나를 제출한 뒤 그 작업 ID만 취소하고 최종 상태를 확인해줘. 다른 프로세스는 종료하지 마.
```

Read-only project discovery; do not request PDK or file contents:

```text
허용된 Cadence 프로젝트 라이브러리와 셀을 나열하고 NOT_gate schematic 뷰의 존재 여부만 확인해줘. 경로나 파일 내용은 출력하지 마.
```

Fixture profile lifecycle; approve only the fixed fixture submission:

```text
fixture-rc-transient 프로파일의 nominal corner를 기본 변수로 실행하고 완료 상태와 artifact metadata만 요약해줘. netlist나 raw waveform 내용은 출력하지 마.
```

Read-only synthetic ADC contract inspection:

```text
adc-synthetic-v1 measurement contract의 버전, 단위, 계산식, FFT 정책을 보여줘. 사용자 회로 값은 추정하지 마.
```

## Recovery

- If `/mcp` does not show the server, restart Codex Desktop once and inspect the MCP server list.
- Run `codex mcp get cadence-mcp-bridge --json` from a PowerShell session where `CODEX_HOME` points
  to `%USERPROFILE%\.codex` when the CLI cannot infer a Unicode Windows home path.
- If registration must be rolled back, close Codex Desktop, preserve the current config, restore
  the newest `config.toml.WP06-*.bak`, and restart. Do not delete unrelated MCP entries.
- SSH, runner, or Spectre failures are diagnosed with `.\scripts\verify-e2e.ps1`; do not add a raw
  command tool as a workaround.
