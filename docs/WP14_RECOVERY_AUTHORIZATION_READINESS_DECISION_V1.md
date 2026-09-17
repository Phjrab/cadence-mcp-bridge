# WP-14 recovery Authorization readiness decision v1

## Decision

- Decision timestamp: `2026-09-17T12:01:58.0318796Z`
- Evidence observation: `2026-09-17T08:05:01Z`
- Evidence expiry boundary: `2026-09-18T08:05:01Z`
- Remaining interval at decision: approximately 20 hours 3 minutes 3 seconds
- Evidence age decision: `WITHIN_24_HOURS_AT_DECISION_ONLY`
- Recovery Authorization readiness: `BLOCKED`
- Execution authority: `false`

PR #39 reviewed head `961b60a93021b116ff96e1a7f594b34b217219a0`
was merged as `7a60affe0aa26b38ec02b6d96bcc3e2fc8660fbd`, verified as the
latest local and remote `origin/main` before this feature branch was created.
Repository visibility remains PUBLIC and `deployment_enabled=false` remains fixed.

This document is a repository-only readiness decision. It is not an Authorization,
activation record, preflight result, approval grant, executor binding or invocation
instruction. It does not alter the request package, evidence, activation, claims,
runner, assets or deployment configuration.

## Why readiness is BLOCKED before evidence expiry

Evidence being inside its 24-hour window is necessary but not sufficient. All of
the following remain independently unresolved:

1. The exact local `executor_binding` has not been freshly verified for an actual
   grant and must not be inferred or published in this PUBLIC repository.
2. No current fixed preflight has verified remote identity, canonical root and
   parents, no active Cadence process, no snapshot/staged temporary artifacts, and
   all eleven exact preimages. Historical diagnostic or collection results are not
   promoted to current state.
3. No exact 17-field Authorization exists. Its UUID, `not_before`, `expires_at`,
   executor binding and explicit one-attempt grants remain unset.
4. The eventual `expires_at` must be later than `not_before`, within the executor's
   24-hour authorization window, and no later than the evidence boundary. A later
   clock check may shorten or eliminate the available window.
5. The original deployment attempt and collection slot are consumed. Their
   activation and claims must remain unchanged; neither can authorize recovery.
6. The independent recovery slot is intentionally unused. A failed, crashed,
   partial or uncertain recovery consumes it permanently before transport.

Therefore no exact Authorization may be prepared or invoked from this decision.
The user must separately review a concrete, locally verified record while evidence
is still valid. A PR merge is not that approval.

## Preserved single-use contract

- The recovery plan, recovery deployer, package, evidence and original deployer
  retain the hashes fixed in the merged request package.
- The original activation hash remains
  `095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`.
- The original six-field claim, original authorization ID and exact consumed time
  `2026-09-17T08:20:37.8800486+00:00` remain required predecessor evidence.
- Both executors must share the existing exclusive `operation.lock`.
- The fixed `recovery-v1.json` slot must use create-new, write-through and durable
  flush before transport. No reset, alternate checkout, retry, cleanup, repair,
  fallback destination or automatic rollback is allowed.
- The proposed future scope remains exactly one fixed preflight, snapshot, eleven
  fixed asset installations and exact final hash/mode/syntax/runner verification.
- The 300-second shared deadline, 65,536-byte per-call combined output limit,
  identity/path/type/owner/link/mode/hash checks and fail-closed behavior remain.
- Cadence/SKILL/discovery/simulation, OA/ADE/design/PDK changes, scientific baseline
  selection and WP-15 remain excluded.

## Mandatory decision at any later run

Recompute current UTC time before creating or reviewing any activation:

- If `now < 2026-09-18T08:05:01Z`, evidence is only temporally eligible. Readiness
  remains BLOCKED until executor identity, the exact record and current preflight
  gates are separately verified and explicitly approved.
- If `now >= 2026-09-18T08:05:01Z`, do not create a recovery Authorization. Record
  `EVIDENCE_EXPIRED` and prepare only a versioned fail-closed evidence-renewal plan.
  The old timestamp/hash and consumed collector slot must not be edited or reused.
  New evidence requires a new bounded collection authority, local publication
  review, and separately reviewed versioned recovery bindings.

No action is allowed exactly at the boundary. There is no automatic transition from
this decision to collection, Authorization creation, remote preflight or deployment.

## Acceptance criteria

1. PR #39 exact head, merge commit and latest `origin/main` are verified.
2. Current UTC time is compared to the fixed evidence boundary without mutation.
3. The decision records evidence as unexpired only at the stated timestamp.
4. Recovery readiness remains BLOCKED despite temporal eligibility.
5. Missing executor identity is neither guessed nor published.
6. Historical diagnostics are not treated as a current preflight.
7. No Authorization, UUID, activation interval, grant or recovery claim is created.
8. Existing activation, claims, evidence, timestamps and hashes are unchanged.
9. Shared locking and durable one-use recovery consumption remain mandatory.
10. Expiry routes only to a separately reviewed evidence-renewal plan.
11. PUBLIC and `deployment_enabled=false` remain unchanged.
12. No SSH/SCP, collection, deployment, Cadence or design operation occurs.
13. Only this decision and `PROJECT_STATE.md` change on the feature branch.
14. Document, hash, security, Git diff and remote feature SHA checks pass before STOP.

## Local verification

A fresh Git-index export with only this decision and `PROJECT_STATE.md` overlaid
contains no ignored activation or operator ledger and has no remote. Ruff and
strict mypy for 17 source files pass. Eighteen focused security tests pass both
directly and through the security gate. Secret preflight covers 362 repository
files, and the strict locked dependency audit reports no known vulnerabilities.
The two-file scope, 14 decision criteria, 206 unique state keys, absent recovery
Authorization, unchanged protected files and false deployment gate pass. No full
test suite or actual integration is rerun for this documentation-only decision.

## Next gate

Integrate this documentary decision only after user review. The next substantive
action depends on the actual clock after integration. It must be either a separately
reviewed exact-Authorization preparation while all evidence and identity gates are
valid, or a fail-closed evidence-renewal plan after expiry. Neither is authorized
by this decision.
