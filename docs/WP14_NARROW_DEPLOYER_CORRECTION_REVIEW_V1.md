# WP-14 Narrow Deployer Correction and Contract Review — Version 1

Date: 2026-09-17

Requested local correction: **VERIFIED**. Remote deployment readiness: **BLOCKED**.

## Authority, provenance and immutable inputs

This execution is authorized only to correct string escaping, add isolated local regressions, and
compare remote identity, timeout, output, and single-use controls with the package. It does not
authorize additional deployment machinery, remote preflight/deployment, SSH/SCP, Cadence, discovery,
simulation, or design access. No live remote authorization record is created.

- Resumed branch: `wp/WP-14-narrow-deployment-attempt`.
- Incoming local and freshly verified remote HEAD: `d074332805dbdf8c826e27c1cf954ed4a0858864`.
- Unchanged origin/main / branch base: `42405e271f54595eae69ca193dc9e3fef30dac94`.
- Repository: `Phjrab/cadence-mcp-bridge`, PRIVATE.
- Immutable approval package normalized-LF SHA-256:
  `7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87`.
- Previous deployer normalized-LF SHA-256:
  `b48b7cb2b24cb3a8ac257031dd6fa79116ea71a4b2117e22226683837692bc1e`.
- Corrected deployer normalized-LF SHA-256:
  `4d2d78bf127534337838fad4f373f8966d986c6bd421b11438d3c81f87c0f623`.

The eleven package assets, two plans, all decision records, deployment result v1, prior approval
audit record, and `deployment_enabled=false` are unchanged. The prior approval is not reusable for
this new hash; the old-hash rejection is exercised only with synthetic temporary records.

## Exact correction

Six deployer statements change, without adding parameters or changing transport/authority logic:

1. Preflight success marker: one shell newline escape.
2. Snapshot TSV formats: one tab/newline escape per separator, including ABSENT entries.
3. Snapshot `find -exec`: one escaped semicolon argument.
4. Snapshot success marker: one shell newline escape.
5. Per-asset install success marker: one shell newline escape.
6. Final verification success marker: one shell newline escape.

The regression suite catches reintroduced double-escaped marker, TSV, and find strings. Generated
commands are captured and lexically inspected, not evaluated. No arbitrary execution interface is
added to the deployer or MCP.

## Isolation and local evidence

`tests/fixtures/wp14_narrow_fake_transport.ps1` is a test-only harness. Pytest copies the deployer,
immutable package, bound plans and eleven assets into a fresh temporary directory containing
spaces. It never copies the live authorization record. A synthetic approval is generated only in
that fixture and binds the copied script's current hash. PowerShell is launched by absolute path;
PATH contains only an empty fixture directory, and both transport names are shadowed by verified
PowerShell functions. A missing fake must not resolve a real transport. Staging is confined to the
fixture's scratch directory. No transport subprocess or shell command is executed.

The successful fake path records exactly 25 calls: preflight, snapshot, eleven upload/install
pairs, and final verification. Every staged upload has the package hash and exact destination;
generated install strings retain the package mode and atomic rename. Fake response decoding tests
the marker regression, while independent lexical assertions check all TSV formats and the find
terminator. The fake does not claim to execute remote filesystem operations or validate Bash.

The 34 focused tests pass, including missing/invalid/old-hash authority, local hash tamper,
WhatIf, nonzero failures, wrong markers, finite output overflow and a deadline already expired
before transport. Failure tests prove no subsequent fake call or automatic retry occurs. A
separate characterization test demonstrates the approval-consumption gap below; it is not proof
that repeated real use is permitted. The first harness trial detected a PowerShell function/native
argument-shape difference for `--`; the harness was corrected without changing production argv.

## Comparison with the immutable deployment contract

| Requirement | Existing implementation and local evidence | Assessment / remaining action |
| --- | --- | --- |
| Remote identity and drift rejection | Fixed alias, strict host-key options, root/parent realpath and symlink checks, and a runner-reported `0.18.0` check. Old file hash/mode is captured during snapshot, not compared with a reviewed preimage manifest before executing/replacing it. | INCOMPLETE. No fixed hostname/user check or expected old-asset presence/hash/mode contract. A modified runner can still self-report 0.18.0. Establish reviewed preimages and reject identity/type drift before invoking or replacing managed files; do not infer current identities from historical repository blobs. |
| Maximum wall clock: 300 seconds | `Assert-WallClock` runs before and after synchronous native calls. Connection/liveness options exist. The expired-before-call test passes. | INCOMPLETE. A live process can block inside the call beyond the total deadline. A hard deadline must supervise owned local transport processes while running, stop subsequent work, and never imply remote rollback or safe retry. No such process-management change was authorized in this escape-only run. |
| Output limit: 65,536 bytes | UTF-8 size is checked after `Out-String` has collected the complete response. Finite oversized SSH/SCP fake responses are rejected without later calls. | INCOMPLETE. Collection is unbounded until process completion; it is not a streaming memory bound. Concurrent bounded stdout/stderr draining and fail-closed overflow handling need separate local hardening and tests. |
| One attempt/use and concurrency one | Authorization declares `max_uses=1`, no retry loop exists, and an existing fixed snapshot blocks a later normal run. The record is not consumed and no operation-wide lock exists. | INCOMPLETE. Two independent fake preflight failures using the same record both reach the fake transport; the record is unchanged. A durable exclusive claim before first transport, including failed/uncertain outcomes, and concurrent-invocation rejection are required. A snapshot created later is not equivalent to one-use consumption. |

These gaps were not silently implemented as part of an escape-only approval. Passing the local
regression suite is not full deployment acceptance. The original implementation document now
states these limitations instead of claiming hard time/output or one-use enforcement.

Additional evidence limits: the current snapshot code captures preimages but these tests do not
verify a recoverable real snapshot or protect against concurrent path replacement. Its combined
`bash -n file1 file2 ...` command does not establish a separate syntax check of every shell file;
each fixed file needs individual validation in future hardening. No current VM identity, lock,
file mode, runner version, or design fingerprint is asserted from this local-only work.

## Local acceptance and remaining authority

- Fixed escaping and isolated regressions: PASS, 34 focused tests.
- No actual SSH/SCP, remote deployment, Cadence/discovery/simulation or design access: preserved.
- Existing package/asset/plan/history preservation and false deployment gate: PASS.
- Ruff and strict `mypy src` (17 source files): PASS.
- Full local pytest: 234 passed, eight deliberately skipped real integrations, 56 existing warnings.
- Security gate: 335-file secret scan, 18 security tests and strict locked dependency audit PASS;
  no known dependency vulnerabilities found.
- Both PowerShell files parse without errors; document/scope/hash checks and `git diff --check` PASS.
- Full deployment gate: BLOCKED on the four control gaps, subsequent review/integration, and a
  new exact-hash remote approval. Neither this document nor a synthetic test record is authority.

The only proposed next work is separately approved repository-side hardening of these controls
with isolated tests. It must preserve the package, eleven assets, false deployment gate, and
historical evidence; any new authorization schema/storage contract must be documented before
remote use. No remote authority should be requested until that local hardening is verified.
Discovery invocation remains a distinct later approval. VDD=1.0 V, VCM=0.5 V and no added external
load remain planning assumptions, and WP-15 remains unstarted.
