# WP-14 post-close diagnostic and bounded recovery plan v1

## Observation, not deployment readiness

At 2026-09-17T08:56:29.420609+00:00, following the user's report of normal
Virtuoso shutdown, one invocation of the unchanged no-argument diagnostic passed
all twelve checks: HOST, USER, NO_CADENCE_PROCESS, ROOT, RUNNER_EXECUTABLE,
SNAPSHOT_ABSENT and PARENT_6 through PARENT_11. Only fixed status enums and the
observation timestamp were returned. No process was terminated by this agent.

This resolves the observed process predicate blocker. It does not establish OA
lock absence, current asset preimages, source fingerprints, source/state semantic
equivalence, or the exact cause of the historical transport failure. The diagnostic
does not read design data, invoke the runner or perform a deployment.

The previous consumed deployment activation, durable claim, result v2, diagnostic
v1 and collection evidence v1 remain unchanged. Deployment attempts remain one;
deployment retries remain zero. PUBLIC and deployment_enabled=false are unchanged.

## Recovery design boundary

This versioned plan is non-executable. It is not a replacement activation record
and does not release a consumed claim. The user's continuation approval permits
preparation of the recovery, but the package-wide single-use contract cannot be
bypassed by changing a UUID, deleting a claim, moving checkouts or patching the
existing executor at invocation time.

The next repository implementation must provide a separately reviewed, fixed
recovery entry point, with no caller-supplied commands, paths or design identifiers.
It must share the original operator concurrency lock and require the original
consumed claim to remain present and bound to activation SHA-256
095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5.
An independent durable recovery claim must be created exclusively and flushed
before any recovery transport. A failed or uncertain recovery consumes that slot;
no fallback, second retry, cleanup or repair is permitted.

The immutable deployment package binding remains
96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431.
The original deployer remains
3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc.
Exactly its eleven reviewed assets, modes, fixed root and snapshot destination
remain eligible. No twelfth asset, alternate backup path or broad deployer is allowed.

Before writes, a separately identified read-only recovery preflight must verify
strict SSH identity, canonical non-symlink root/parents, no active Cadence process,
no snapshot or staged temporary artifacts, and all eleven exact preimages against
reviewed evidence 0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7.
Evidence must be at most 24 hours old at execution; expiration or any drift blocks
without refreshing authority implicitly. Fresh observations must retain closed
schema and bounded metadata only. The old collector's consumed slot is not reused.

Only after all prerequisites may the fixed sequence create the original snapshot,
verify before-image hashes, install exactly eleven assets atomically per file,
and verify final hashes, modes, syntax and runner 0.19.0. Partial installation is
not atomic as a whole and must be reported as such, with no automatic rollback.
Cadence, discovery, simulation and OA/ADE/design/PDK changes remain outside this
recovery. Scientific baseline remains unconfirmed.

## Acceptance criteria for the next implementation

1. Original authorization, claim, immutable package, eleven assets and evidence are preserved.
2. No generic shell/SKILL/MCP interface or caller-controlled target exists.
3. Original consumed claim linkage is mandatory; missing/malformed/mismatched claims fail locally.
4. Recovery activation binds exact recovery implementation and plan hashes, executor and expiry.
5. Both executors share exclusive concurrency control; recovery has one durable independent slot.
6. Repeated, concurrent, crashed and failed recovery attempts cannot start a second transport.
7. Strict identity and eleven type/owner/link/mode/hash or explicit-absence checks precede writes.
8. Process, snapshot, temporary-file, symlink and freshness failures stop without cleanup.
9. Shared 300-second deadline and 65,536-byte combined per-call output cap remain enforced.
10. No stderr/raw process output, credentials, raw OA/ADE/PDK content or active grant is published.
11. Snapshot preimages are verified before replacement; every replacement rechecks its preimage.
12. Final exact hash/mode/version verification is mandatory; uncertainty is not success.
13. Fake-transport local tests exercise positive flow and every negative gate before remote use.
14. Ruff, mypy, local tests, security checks and document/hash preservation pass.
15. A final-hash-bound recovery authorization is required before execution; this plan grants none.

## This checkpoint

No recovery executor or activation was created and no deployment was retried.
The next substantive step is recovery implementation and isolated local validation,
not another state-only merge cycle. Feature integration still requires the user's
specific branch/PR approval. WP-15 remains unstarted.
