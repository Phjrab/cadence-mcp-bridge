# Native ADE MCP integration

Date: 2026-09-30. User-selected phase: `NATIVE-MCP-01`.
Outcome: fixed native DC/AC/trap TRAN submission and reusable result reads verified
through an actual subprocess stdio MCP client. Specification: `not_evaluated`.

## Interface and execution

Four tools extend the registry from 31 to 35:

| Tool | Contract |
| --- | --- |
| `cadence_list_native_diagnostics` | List fixed revision, operating point and settings; no remote execution |
| `cadence_submit_native_diagnostic` | Submit one native DC, AC or trap TRAN bundle with caller UUID4 |
| `cadence_native_diagnostic_status` | Read separate netlisting, simulator and extraction stages |
| `cadence_native_diagnostic_result` | Return seven DC scalars, 71 AC spectrum points or a bounded TRAN summary with provenance |

Requests accept only `operation_id`, `analysis` (`dc`, `ac`, `tran`),
`revision_id=wp14-native-ade-v1` and
`operating_point_id=candidate-320-702mv-v1`. Generate a new lowercase UUID4 once
for a new operation and retain it across communication failures. Reusing an
existing ID reads its status; completed, failed or uncertain jobs never execute
again. A different analysis for that ID is rejected. Lost-worker status is
`unknown`, retains the claim and prevents another execution from guessing success.

Each job copies the original saved ADE state into its owned directory, changes
only the two candidate expressions, loads the state, generates the native input,
verifies effective conditions, reserves the shared cumulative budget, runs Spectre
and extracts qualified PSF measurements. Immutable existing native guards and
readers are reused. No caller path, netlist, signal expression, script, voltage
range or generic command is accepted. Raw PSF, circuit data, ADE state and logs
remain private. The source, copy, state, model, circuit, generated input, owned
variables, PSF and measurement-frame digests accompany the bounded result.

Original saved biases remain 300/650 mV. The actual owned-state biases are
320/702 mV. VDD=1.0 V, NN, 27 C, VCM=0.5 V and existing topology/load/stimulus
are verified under the native baseline fingerprints. The original saved state
enables DC only; AC/TRAN controls are explicit job settings. AC covers 10 Hz to
100 MHz at ten points per decade with differential 1 V complex excitation.
TRAN covers 0–4 ms, maxstep=10 us, `method=trap`, with the existing opposed
1 kHz, 50 mV peak inputs (100 mV peak differential). No numerical design goal
or original-source promotion is introduced.

## Real stdio E2E and comparison

The client starts the bridge as a separate process using the installed MCP SDK,
discovers all 35 tools, and exercises listing, submit, polling, result, repeated
submission and wrong-analysis rejection. New native runs use the qualified fixed
candidate. Prior native candidate and baseline evidence is reused for comparison.

| Analysis | Observed result | Difference from preserved candidate |
| --- | --- | --- |
| DC | Seven scalars; output common mode 0.2277073 V, differential 0 V | Maximum absolute scalar difference 0 V |
| AC | 71 points; gain at 10 Hz 78.951961907 dB | Maximum relative gain and phase differences 0 |
| Trap TRAN | 754 adaptive points; differential extrema −0.9992316221 / +0.9992359621 V | Same point count; maximum absolute reported-extrema difference 0 V |

All three simulations and readers succeeded with zero errors, two allowlisted
CMI-2477 warnings and zero notices. Typed validation and remote frame recalculation
check measurement arithmetic, selectors, source/state conditions, flags and digests.
Comparison tolerances are regression tolerances, not design specifications.
Full waveform equivalence, small-signal linearity under the large TRAN excitation,
THD/SNDR/ENOB, settling, Noise/STB, PVT or statistics are not qualified here.

Repeated submits before and after completion did not consume extra attempts.
Wrong-analysis requests were rejected for each job. Final postflight verified
protected original/PDK/history and reference results, zero active EDA processes,
absence of the active claim, owned-job containment and result-volume limits.

## Transport correction and protected checkpoint

The initial stdio submit returned SSH exit 255 with empty output before remote job
creation. The same DC operation ID was submitted once through the fixed operator
path during diagnosis and completed; the resumed MCP test reused that DC result.
The first failure console and pre-correction journal were preserved as immutable
private copies. No simulation was replayed to repair communication.

A controlled read-only comparison isolated the cause: MCP's default inherited
Windows environment omits `PROGRAMDATA`; this Windows OpenSSH fails silently
without it. Adding only that variable restored the fixed status read. The bridge
now uses the Windows common-application-data known-folder API when the variable
is absent, preserves an existing value and fails closed when resolution fails.
SSH stdin is explicitly `DEVNULL` to isolate it from the MCP protocol stream.
BatchMode, host-key checks, shell-free argv and output limits remain enforced.

This change consumed one of three correction allowances. Remote v1 assets,
manifest and policy remain unchanged; no remote correction deployment occurred.
Prior counters remain DC five of six, native AC/TRAN three of three, and candidate
one of three. The elapsed ceiling remains removed.

## Resources and evidence

Three new Spectre attempts increased shared cumulative use from 21 to 24 of 100.
Reserved result bytes increased from 1,611,661,312 to 2,014,314,496 under 5 GiB.
The DC/AC/TRAN jobs occupy 271,200 / 311,421 / 667,911 bytes. Final free space is
25,822,081,024 bytes (approximately 24.05 GiB), above the greater-of-2-GiB-or-10%
floor. EDA concurrency never exceeds one; final active EDA count and paid usage
are zero.

Deployment checked exact file manifests, Bash syntax and real Python 2.6 compile
and preflight. Native/SSH focused tests: 77 passed. Ruff and strict mypy passed.
The security suite passed 18 tests, and the frozen dependency audit found no known
vulnerabilities. The subsequent focused rerun passed all 80 native/SSH/installer
tests. Exact deployment policy/file hashes, unique state keys and live typed
results passed validation; secret preflight passed for 624 repository files.
Full regression passed 835 tests with eight opt-in remote integration skips and
56 existing deprecation warnings. Skips are not PASS; the native live stdio E2E
is the separately scoped validation above. The initial regression's missing
native backend allowlist entries were corrected and verified in the passing
rerun. The installer prompt addition was separately covered by the latest
80-test focused run. Public scope review covered all 25 feature files, and
staged remote asset blobs match the immutable deployed manifest exactly.

Private stdio E2E report: `.codex/native-mcp-v1-e2e-private.json`, SHA-256
`ab55c504712b50726953216a847eb59d828f5abb057702bf0510260bacd08d60`.
Unchanged remote policy SHA-256:
`5f47cac62b2a6a6c2a19166264ae9ba5c09b0fd4e4c0b95c9509f6d4746ee384`.
Manifest SHA-256:
`35ab29537f977541c8b973f24c164cece4b4926440a2d32bcb7d1bfc34c87276`.
Preserved candidate reference SHA-256:
`8fccdd046961894e45a9788074b815839ec466892cae558fcd6ab716ebec5c88`.
Private authority, identity, failure logs, ledgers, frames and raw design data are
excluded from the feature PR. Only reviewed code, contracts and aggregates are
published.

## Phase exit

The fixed native candidate workflow is available as reusable MCP submission,
status and measurement tools. No numerical specification PASS is claimed.
Ask once before another major phase; no extra voltage range, original write,
optimization, sweep or statistical analysis is active.

Proposed next phase: `ADE-PVT-PREP-01`, a protected read of this PDK's actual
corner/statistics definitions and installed execution support, followed by a
minimal qualification plan. Do not infer FF/SS or Monte Carlo availability.
No new circuit execution is part of that preparation proposal. Recommended
model/effort: GPT-6.1 Sol, high. Exact proposed start prompt:

> ADE-PVT-PREP-01을 승인한다. 현재 PDK의 실제 corner·statistics 정의와 설치된
> 실행 능력을 보호된 조회로 확인하고, 지원 범위와 최소 검증 계획을 보고하라.
> 원본·PDK·기존 결과와 누적 예산을 유지하며 임의 corner나 수치 목표를 만들지
> 마라. 조사·필요한 코드·시험·관리영역 배포·feature PR 검토·병합은 자율
> 진행하고, 이 준비 단계에는 새 회로 실행을 포함하지 마라. 단계 끝에 다음
> 단계 진행 여부를 한 번 묻고 멈춰라.
