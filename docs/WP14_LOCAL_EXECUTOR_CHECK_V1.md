# WP-14 independent local executor check v1

## Scope and time gate

Implementation began at `2026-09-18T04:31:55Z`, before the evidence boundary
`2026-09-18T08:05:01Z`. Base main is PR #41 merge
`1a673fae8a8e9741b7ea46eccde83de08e444127`. PUBLIC and
`deployment_enabled=false` remain fixed. This document records repository
implementation, not an Authorization or an execution grant.

## Interface and semantics

`scripts/verify-wp14-executor.ps1` is a standalone operator-only PowerShell 7.5+
Windows script. It has no parameters or MCP registration. All caller arguments,
including `-WhatIf`, are rejected. The fixed sibling recovery deployer is read as
bounded text, never executed, dot-sourced, imported or parsed into executable code.
Its normalized-LF SHA-256 must remain
`e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374`.
Reparse ancestors, a missing/non-file deployer, or a deployer above 128 KiB fail.

On a future separately scoped actual invocation, the checker reads the current
Windows SID and MachineGuid twice, accepts only a bounded Windows account SID and
nonzero GUID shape, requires exact equality between reads, and computes the exact
lowercase SHA-256 of UTF-8 `SID|MachineGuid` in memory. It never trims or normalizes
case. Unsupported SID forms fail closed rather than selecting another identity.
Identity values and digests are never output or persisted. Managed-memory references
are released; this is not a guarantee of cryptographic erasure of managed strings.

Output is one JSON line with exactly Boolean `success` and enum `code`, below 128
bytes. Exit code is zero on success and one on failure. Allowed codes are:

- `LOCAL_RULE_READY`
- `ARGUMENTS_NOT_ALLOWED`
- `UNSUPPORTED_RUNTIME`
- `DEPLOYER_INTEGRITY_FAILED`
- `IDENTITY_UNAVAILABLE`
- `IDENTITY_INVALID`
- `IDENTITY_CHANGED`
- `LOCAL_CHECK_FAILED`

Raw exceptions are suppressed. Syntax/interpreter startup failures occur outside
the script protocol and must be treated by the operator as failure. Local OS API
reads have no internal cancellation guarantee; isolated test processes have a
15-second bound. The checker performs no network, ledger, lock or file write.

`LOCAL_RULE_READY` means only supported, stable local identity inputs and a
computable rule. It is not a comparison to any Authorization, remote verification,
evidence freshness result or permission to deploy. An existing collector uses
`username|MachineGuid`; its digest must not be substituted for this SID-based rule.

## Verification boundary

Tests copy the checker and unchanged deployer into temporary directories, replace
only the identity acquisition function with synthetic inputs, and assert the live
identity primitives are absent before launching PowerShell. There is no production
fixture flag, injected identity argument or caller-controlled executable path.
Tests independently compute a known synthetic digest with Python, check success
and failure envelopes, reject a username in place of SID, suppress sensitive
exceptions, detect identity changes and deployer tampering, reject unsupported
runtime and arguments, and verify no files change during a successful check.

The original production checker was not invoked. No actual identity or binding was
read or generated. No actual or synthetic Authorization, claim or lock is needed by
these new tests. Existing recovery/deployment executors and eleven assets are
unchanged. Prior evidence and consumed records remain preserved.

## Acceptance criteria

1. Time at implementation start precedes the fixed evidence boundary.
2. Base main equals the verified PR #41 merge commit.
3. Standalone no-argument, operator-only checker has no MCP registration.
4. Fixed recovery deployer hash is verified without executing it.
5. SID and MachineGuid use exact original strings and the deployer's digest rule.
6. Identity failures, invalid shapes and changes between reads fail closed.
7. Only the closed success/code envelope is returned; no raw values or digest leak.
8. Tests use only synthetic identities and assert live identity access is removed.
9. No Authorization, claim, lock, transport or design operation occurs.
10. PUBLIC, the false deployment gate and protected artifacts remain unchanged.
11. Focused local tests, static checks, security checks and document checks pass.
12. Feature commit/push is verified before STOP; main and WP-15 remain untouched.

## Local results

Checker normalized-LF SHA-256:
`39cc05f53097f3d8847e473200f140e9e9f283eddd04f194f5e7e69c96bfe975`.
The final isolated run passed 37 tests (19 synthetic checker tests and 18 security
tests). Ruff and strict mypy for 17 source files passed. The security gate repeated
the 18 security tests, scanned 366 repository files and reported no known locked
dependency vulnerabilities. An initial unnecessary-encoding Ruff finding in the
new test was corrected before the final passing checks.

Document checks passed for the four-file scope, unique state keys, false gates,
absent recovery Authorization and protected tracked artifact preservation. The
existing full deployment/recovery suite was not rerun: the deployers are unchanged,
and this task permits only synthetic identity tests without Authorization/claim
fixtures. No actual checker or remote integration was invoked.

## Next boundary

Review/integrate this repository implementation first. Any later actual identity
check needs its own bounded task and must re-evaluate the evidence clock. At or
after `2026-09-18T08:05:01Z`, the current recovery evidence is ineligible: preserve
its timestamp/hash and consumed claims and prepare a versioned renewal plan.
This helper cannot refresh evidence or bypass that boundary.
