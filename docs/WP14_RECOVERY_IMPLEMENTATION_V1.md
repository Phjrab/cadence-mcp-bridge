# WP-14 fixed recovery implementation v1

Scope: repository implementation and isolated local validation only. No recovery
authorization, real ledger, SSH/SCP, remote write or Cadence invocation is created.

## Bindings

- Plan: WP14_POST_CLOSE_RECOVERY_PLAN_V1.md, normalized-LF SHA-256
  5333c6915c06ca1897b3e282e1de48cc16564fbfd37fcbdfe05a1907edb30d3a.
- Candidate: scripts/deploy-wp14-recovery.ps1, normalized-LF SHA-256
  e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374.
- Original deployer remains unchanged at
  3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc.

## Separate recovery contract

The argument-free operator-only candidate statically retains the original eleven
assets and transport/install sequence. It does not rewrite or invoke the original
script. A regression assertion compares the full transport and remote sequence
with the original to prevent unnoticed divergence. Maintaining two executors has
a duplication cost; future changes must review both, not silently update bindings.

The separate activation path is
docs/approvals/WP14_NARROW_RECOVERY_AUTHORIZATION_V1.json (not created).
It retains the original closed schema_version=2 structure and adds exactly one
string field recovery_plan_sha256. record_kind must instead equal
explicit_single_recovery_deployment_authorization. The self hash must bind this
candidate, and the plan/evidence hashes are fixed. Old deployment authority cannot
activate recovery. Executor, maximum one use, 24-hour validity/evidence age, strict
identity and exact eleven preimages remain mandatory.

Under the original exclusive operation.lock, the executor requires the preserved
predecessor claim to match all six fixed fields, with a 4096-byte limit, duplicate
key rejection, scalar types and reparse-ancestor rejection. It separately verifies
the preserved original activation hash. No raw activation or local identity is
printed or published. Missing, malformed or mismatched predecessor records stop
before recovery consumption or transport.

The new fixed recovery-v1.json slot uses CreateNew, WriteThrough and Flush(true)
under the SAME operator ledger and exclusive lock. The original claim is never
removed or changed. A zero-length, failed or uncertain recovery claim blocks any
later attempt. New UUIDs/checkouts cannot reset either slot. The new claim records
the predecessor activation and plan hashes as well as the new activation binding.

The fixed preflight, snapshot, eleven uploads/installs and final verification keep
the original 300-second shared deadline and bounded output controls. Snapshot or
temporary artifacts and preimage drift stop without cleanup. Remote per-file
atomic installs are not a whole-deployment transaction. No automatic rollback,
discovery, simulation, OA save or scientific baseline approval is added.

## Local verification and limits

Tests use temporary repository copies, synthetic activation/claim data and the
existing fake process. Only those copies substitute the executable, ledger and
synthetic hashes; production has no test bypass. The fake server reads the recovery
activation rather than the preserved predecessor activation. Tests cover the
25-call success sequence, no additional calls after consumption, failed-preflight
consumption, missing/empty/wrong/array/extra/duplicate predecessors, preserved
activation tamper, existing recovery claim and plan/evidence/kind binding rejection.

These tests do not prove current VM state or approve execution. Prior evidence is
dated 2026-09-17T08:05:01Z; its 24-hour validity must be evaluated at any later
attempt, not assumed from this local checkpoint. A new evidence version cannot be
substituted without a reviewed contract/hash change. PUBLIC and
deployment_enabled=false remain unchanged. Final hash-bound recovery authority
and review remain required before any real recovery invocation. WP-15 is unstarted.

## Validation checkpoint: PARTIAL, not ready for deployment

Ruff, strict mypy (17 source files), PowerShell parsing, state-key uniqueness,
protected-file comparison, 358-file secret preflight, 18 security tests and strict
dependency audit passed. The dedicated recovery suite passed all 15 tests using
fake transport. The preserved real activation hash was checked without printing
its contents; the new recovery activation remains absent.

The first full working-copy run reported 358 passed and four failures: two test
assertions using an outdated cumulative-call interpretation (corrected and rerun),
and two historical assertions requiring no local deployment activation. The latter
conflict with the explicit requirement to preserve the consumed activation. No
test was weakened and no real evidence was removed to obtain a passing result.

A clean Git-index export excluded ignored local activation evidence and ran the
entire suite: 353 passed, nine failed, three remote tests skipped and five remote
tests deselected. All nine failures were existing default-encoding reads of UTF-8
fixture scripts containing a Korean temporary interpreter path (CP949 decode
errors), before fake transport. With PYTHONUTF8=1 and python -X utf8, eight passed;
one existing stderr test failed because its three-second shared budget produced
zero calls rather than the expected one. Its isolated rerun passed in 4.38 seconds.
The precise scheduling cause remains unproven; no production timeout was changed.

These reruns do NOT constitute one clean full-suite PASS. Repository acceptance
remains PARTIAL pending explicit UTF-8 fixture handling and deterministic separation
of startup-budget and stderr tests, followed by a full isolated run. This is the
next local task, before merge or remote execution. Do not remove preserved grants,
weaken production deadlines, or claim deployment readiness to resolve test failures.
