# WP-14 single-use recovery approval request v1

## Authority: request only, not a grant

Record kind: approval_request_not_grant. All execution permissions remain false.
This Markdown request is not an executable Authorization and is not placed at the
activation path. No UUID, executor identity, activation interval or claim is created.
PUBLIC and deployment_enabled=false remain mandatory. WP-14 execution is BLOCKED.

PR #38 reviewed head 4dde259134b3d7444723253824679c997a293e67 was merged as
40a459379eb2a2f73719a6929d1e9a4fc496ff1f, verified as latest origin/main.

## Immutable normalized-LF SHA-256 bindings

| Artifact | SHA-256 |
| --- | --- |
| Recovery plan v1 | 5333c6915c06ca1897b3e282e1de48cc16564fbfd37fcbdfe05a1907edb30d3a |
| Recovery deployer | e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374 |
| Deployment package v2 | 96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431 |
| Evidence v1 | 0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7 |
| Original deployer | 3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc |

Original activation required binding remains
095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5.
No existing plan, asset, evidence, activation or claim is changed.

## Freshness and blockers

Clock checked: 2026-09-17T11:37:17Z. Evidence observed_at remains
2026-09-17T08:05:01Z; age is 3h32m16s, within 24 hours at this check only.
Boundary: 2026-09-18T08:05:01Z (17:05:01 Asia/Seoul).
Recheck time at any later approval and invocation. Beyond the boundary, approval
preparation is BLOCKED and requires a separate evidence renewal contract.
Never edit the timestamp/hash or reset the consumed collector slot. New evidence
also needs separately reviewed versioned recovery bindings: the candidate pins v1.

Current identity, eleven preimages, process/lock state, snapshot and temporary-file
absence remain unverified. Dated evidence and diagnostic PASS are not fresh remote
verification. No final approval, new executor binding or activation interval exists.
Scientific conditions, source/state equivalence and snapshot freshness remain
unresolved. No unknown value is inferred or promoted to a scientific baseline.

## Exact future activation fields: requirements, not instantiated values

| Field | Required future content |
| --- | --- |
| schema_version | integer 2 |
| record_kind | explicit_single_recovery_deployment_authorization |
| status | APPROVED only after separate explicit approval |
| package_normalized_lf_sha256 | fixed package hash above |
| deployer_normalized_lf_sha256 | fixed recovery deployer hash above |
| remote_preflight_authorized | explicit future grant; not granted here |
| remote_deployment_authorized | explicit future grant; not granted here |
| max_uses | integer 1 |
| authorization_id | new reviewed UUID; unset |
| not_before | reviewed timezone-aware timestamp; unset |
| expires_at | after not_before; window at most 24h and no later than evidence boundary; unset |
| executor_binding | locally verified exact operator/machine binding; unknown, never guessed or published |
| remote_identity | closed hostname/user/root/verified fields matching fixed contract and reviewed evidence |
| preimages | eleven unique allowlisted path/presence/sha256/mode objects from reviewed evidence |
| evidence_sha256 | unchanged evidence v1 hash above |
| observed_at | unchanged evidence observation above |
| recovery_plan_sha256 | unchanged plan hash above |

The future closed schema contains exactly these 17 fields. Missing fields cannot
be supplied by examples, defaults or PR merge approval. Actual grants and local
identity must not be committed to this PUBLIC repository. The activation path
docs/approvals/WP14_NARROW_RECOVERY_AUTHORIZATION_V1.json remains absent.

## Single-use and preservation

Preserve the original activation and consumed collection/deployment claims without
deletion, rename, overwrite or reset. The candidate validates the original six-field
claim, original ID and hashes, consumed state and exact consumed_at
2026-09-17T08:20:37.8800486+00:00 under the original exclusive operation.lock.
Both executors share that operator lock across checkouts.

The independent fixed recovery-v1.json slot uses CreateNew, WriteThrough and
Flush(true) before transport. Empty, failed, crashed or uncertain consumption
prevents reuse. UUID changes or new checkouts cannot reset either slot. No retry,
cleanup, repair, fallback or automatic rollback is requested.

## Future bounded scope, only after separate explicit approval

One fixed preflight, then only if all gates pass the original snapshot, exactly
eleven fixed asset installs and final hash/mode/syntax/runner 0.19.0 verification.
Preserve strict SSH identity/host-key, owner/type/link/path/preimage checks,
300-second shared deadline and 65,536-byte combined per-call output cap.
Reject stderr, invalid/excessive output and uncertain results. Per-file atomic
replacement is not an atomic deployment; partial installation must be reported.
No twelfth asset, alternate destination or broad deployer is permitted.

Even this proposed future scope excludes Cadence/SKILL/discovery/simulation,
OA write/save, ADE/design/PDK changes, scientific baseline selection and WP-15.
The global deployment_enabled flag remains false.

## Acceptance criteria

1. Verify PR #38 exact head/merge and latest main before branching.
2. Preserve PUBLIC and deployment_enabled=false.
3. Recompute five repository artifact hashes and preserve eleven fixed assets.
4. Preserve original activation and consumed claims; do not open/consume a slot.
5. Record clock, evidence observation, age and fixed boundary unchanged.
6. Expiration blocks approval preparation and requires a separate renewal contract.
7. Specify all 17 future fields without inferring identity, UUID or time interval.
8. Do not create executable Authorization, actual grant or new ledger.
9. Require exact reviewed preimages; no invented identity/hash/mode/absence.
10. Preserve shared lock and independent durable single-use recovery claim.
11. Failed/uncertain attempts consume the slot; no retry/cleanup/repair.
12. Preserve time/output/path/identity/snapshot/final-verification controls.
13. Distinguish local validation and historical evidence from current remote truth.
14. Preserve scientific blockers and all Cadence/design/discovery exclusions.
15. Change only this request and PROJECT_STATE.md; retain prior history.
16. Pass document/hash/security checks, feature commit/push, verify SHA and STOP.

## Next gate

Local validation: all five repository hashes match; 16 criteria, unique state keys
and absent recovery activation pass. Ruff, mypy (17 source files), 18 security
tests and a 361-file secret scan pass in the prior isolated validation copy with
only these documents overlaid and no actual activation/ledger. The initial sandbox
attempt could not start uv; the permitted local rerun passed. No full-suite,
dependency-audit or actual integration rerun is claimed for this documentary change.

Explicit user review and PR integration of this request, not execution approval.
Later activation still requires concrete verified identity, an actual-clock check,
a separately reviewed exact record and explicit one-attempt approval. If evidence
has expired, do not proceed to activation.
