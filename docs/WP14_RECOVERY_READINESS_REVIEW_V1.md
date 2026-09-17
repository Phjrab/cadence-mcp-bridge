# WP-14 recovery deployment readiness review v1

## Scope and verdict

Review timestamp: 2026-09-17T11:09:47Z. This is a non-executable review, not an
authorization record, approval grant, preflight or invocation instruction.
Documentary readiness review: PASS. Remote recovery readiness: BLOCKED.

PR #37 is MERGED with reviewed head
`5f10a9b417af3fbbd7b40d2135eabd8df8bc4d16` and merge commit
`79bb9c170d6822664438493cd4e3e56eb5c83b7c`, verified as latest fetched and remote
main before this feature was created. PUBLIC and deployment_enabled=false remain.
The 365-test clean-copy PASS in WP14_TEST_STABILIZATION_V1.md supersedes only the
historical local-test blocker in WP14_RECOVERY_IMPLEMENTATION_V1.md. Neither that
PASS nor PR integration grants recovery execution authority.

## Verified immutable normalized-LF SHA-256 bindings

| Artifact | SHA-256 |
| --- | --- |
| Recovery plan v1 | 5333c6915c06ca1897b3e282e1de48cc16564fbfd37fcbdfe05a1907edb30d3a |
| Recovery candidate | e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374 |
| Original narrow deployer | 3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc |
| Deployment request package v2 | 96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431 |
| Identity/preimage evidence v1 | 0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7 |

The candidate retains exactly eleven fixed assets. No artifact above is edited.

## Freshness versus current identity

Evidence observed_at is 2026-09-17T08:05:01Z. At the review timestamp its age is
3 hours 4 minutes 46 seconds: within the existing maximum 24-hour age. The age
boundary is 2026-09-18T08:05:01Z (17:05:01 Asia/Seoul). The implementation rejects
age greater than 24 hours at validation; do not plan an operation at the boundary.
An eventual authorization expiry should end no later than this boundary and must
also satisfy the executor's independent maximum 24-hour authorization window.
No not_before, expires_at, UUID or executor identity is selected by this review.

This time calculation is NOT fresh remote identity, preimage, lock or process
verification. The historical twelve-check diagnostic at
2026-09-17T08:56:29.420609+00:00 is not full preflight. Current VM state, snapshot
absence, temporary-artifact absence and all eleven current preimages remain
unverified without separately authorized fixed preflight. No SSH is performed.

The candidate pins evidence v1's exact hash. Once expired, updating a timestamp,
substituting new evidence or reusing the consumed collector slot is prohibited.
Fresh collection would require a separately reviewed bounded collection/recovery
contract preserving the original consumed slot, explicit execution authority,
reviewed new evidence and new versioned recovery bindings. None is created here.

## Preserved predecessor and concurrency conditions

The original activation hash must remain
`095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`.
The candidate checks the original six-field claim, its consumed state, original
authorization ID, package/deployer hashes and exact consumed_at
2026-09-17T08:20:37.8800486+00:00. It rejects absent, oversized, malformed,
duplicate, non-scalar, mismatched or reparse-linked predecessor data.
Existing activation and claims must not be deleted, rewritten, renamed or reset.

Both executors share the original exclusive operation.lock. The candidate has a
separate fixed recovery-v1.json slot, created exclusively with durable flushing
before transport. Failed, incomplete and uncertain consumption all prevent reuse.
This review does not open the lock, invoke the executor, create a claim or claim
that another process cannot race a later operation. Those checks must be repeated
under the executor's lock if separately authorized later.

## Required future grant; absent, not supplied by this document

The recovery activation path remains absent. A future separately reviewed grant
would need exactly the closed 17-field schema enforced by the candidate:

- schema_version=2; record_kind=explicit_single_recovery_deployment_authorization;
  status=APPROVED. These are schema requirements, not the status of this review.
- package_normalized_lf_sha256, deployer_normalized_lf_sha256,
  recovery_plan_sha256 and evidence_sha256 must match the bindings above.
- remote_preflight_authorized and remote_deployment_authorized must be explicitly
  granted; max_uses must be 1. No other execution is included.
- authorization_id, not_before, expires_at and executor_binding must be newly
  reviewed, concrete and locally verified; no invented MachineGuid or identity.
- observed_at must retain the evidence timestamp; remote_identity must contain
  only the four required hostname/user/root/verified fields matching fixed identity.
- preimages must contain exactly eleven unique allowlisted paths, with the closed
  path/presence/sha256/mode schema and exact reviewed hashes/modes or allowed absence.

No completed activation template, secret, local identity or raw grant is published.
Creation itself and one invocation require explicit future approval. Old broad
continuation or PR merge approval cannot replace it.

## Acceptance criteria

1. PR #37 exact reviewed head, merge and main reflection are verified.
2. PUBLIC and deployment_enabled=false are preserved.
3. All five bindings above are recomputed and match; eleven assets are unchanged.
4. Evidence age and its explicit boundary are recorded without timestamp edits.
5. Current remote conditions remain unverified; dated diagnostics are not promoted.
6. The prior failed attempt and consumed activation/claims remain untouched.
7. Recovery activation remains absent; no new local execution ledger is created.
8. The exact new grant fields, time/executor/evidence bindings and one-use rules
   are documented without producing an executable authorization.
9. Expiration requires separate reviewed collection/binding work, never slot reset.
10. Shared locking, durable consumption, no retry/cleanup and no whole-deployment
    atomicity claim remain explicit. Per-file atomic installation is not rollback.
11. The 300-second shared deadline, 65,536-byte output bound, eleven-asset allowlist
    and fixed preflight/snapshot/final verification are not weakened.
12. VDD/VCM/load assumptions, source/state equivalence, snapshot freshness and
    scientific baseline remain unverified or conditional, not deployment outputs.
13. Only this review and PROJECT_STATE.md change; prior history remains intact.
14. Document checks and appropriate isolated local checks pass before feature push.
15. No authorization, SSH/SCP, collection, deployment, Cadence, design change,
    main push/merge or WP-15 work occurs; stop after remote feature SHA verification.

## Local verification

Validation uses a fresh Git-index export with only the two proposed documents
overlaid, no Git remote and no ignored real activation or operator ledger. Ruff
and strict mypy (17 source files) pass. The fixed fake-transport recovery suite
and security tests pass together: 33 passed in 63.09 seconds. The security gate
also repeats all 18 security tests and scans 360 files successfully. The strict
locked dependency audit passes with no known vulnerabilities (using documented
PYTHONIOENCODING=utf-8 for the local audit subprocess). No full-suite
rerun or actual integration is claimed for this two-document-only change; the
previous 365-test result remains historical. Unique state keys (195), fifteen
criteria, preserved prior progress log, unchanged protected metadata/files and
absent recovery activation were checked directly.

## Next decision

Review and explicitly authorize PR integration of this documentary checkpoint.
After integration, decide the next bounded task using the actual clock: if pinned
evidence has expired, plan a new evidence-collection contract before any recovery
grant; otherwise a separately reviewed exact recovery grant is still required.
Do not automatically execute either path. Remote recovery remains BLOCKED.
