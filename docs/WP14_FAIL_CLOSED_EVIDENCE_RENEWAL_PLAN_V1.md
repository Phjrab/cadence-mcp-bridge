# WP-14 fail-closed remote evidence renewal plan v1

## Decision and boundary

- Plan status: `REVIEW_ONLY_BLOCKED`.
- Checked UTC: `2026-09-28T08:44:26.9415628Z`.
- Starting `origin/main`: `ece52c7a44befe34d61215c19f9fa39ab2af5384` (PR #45).
- Old evidence observation: `2026-09-17T08:05:01Z`.
- Old evidence expiry boundary: `2026-09-18T08:05:01Z`.
- Result: `EVIDENCE_EXPIRED`; the old evidence cannot support a recovery Authorization or deployment.
- Repository visibility: PUBLIC; `deployment_enabled=false`.

This versioned document is a plan and acceptance contract only. It creates no
Authorization, activation, claim, lock, executor binding, evidence, deployment
authority, or scientific baseline. It permits no transport, Cadence operation,
or design mutation. WP-14 remains blocked and WP-15 does not start.

## Preserved lineage

1. Preserve `docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V1.json`
   byte-for-byte, including its `observed_at` field and normalized-LF SHA-256
   `0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7`.
   The historical summary is eleven assets, seven present, four allowed absent,
   and zero blockers **at the old observation time only**.
2. Preserve the consumed collection authorization lineage identified by SHA-256
   `631d6dff580edb449cac6b4d342930428bd49bc7fd3337053c9932737a581a20`.
   Preserve its durable consumed claim and original timestamp. Do not delete,
   rewrite, rename, reset, or reinterpret either item as a fresh grant.
3. Preserve the failed deployment activation, its SHA-256
   `095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`,
   and its original six-field claim with
   `consumed_at=2026-09-17T08:20:37.8800486+00:00`.
4. Preserve the original recovery plan, candidate deployer, approval packages,
   eleven asset definitions, and V1-V4 design evidence. Historical hashes and
   dates remain historical; a newer timestamp must never be assigned to an old
   observation.

## Renewal contract to prepare in a separate WP-14 run

1. Create a **new versioned, request-only collection contract** from the reviewed
   PUBLIC-policy version-2 package. It must fix the same remote identity
   (`cadence-vm`, `cadence`, `buet`, canonical `.cadence_mcp` root) and the same
   eleven managed assets. It must explicitly explain why the original collector's
   package-wide single-use claim makes its activation path and attempt unusable.
2. Define a distinct versioned authorization and claim namespace for one new
   collection attempt **only after** an independent review and explicit approval
   of that exact contract and implementation. Reuse the existing operator-local
   global operation lock across versions and check the prior consumed claim as
   immutable lineage. A version bump or new checkout alone never grants another
   attempt. Do not invent an authorization ID, time window, executor identity,
   path, or claim in this plan.
3. If code changes are required to enforce that separation, propose a repository
   implementation and isolated fake-transport tests as their own review gate.
   The current collector hash
   `b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c`
   is historical provenance, not authority to rerun it. A changed collector
   needs a new reviewed normalized-LF hash and matching request package.
4. Retain an argument-free, operator-only, non-MCP, read-only collector. Any
   future authorized attempt must use fixed Windows System32 OpenSSH with
   BatchMode and strict host-key checking, one process and attempt, a shared
   60-second deadline, at most 32,768 combined output bytes, strict UTF-8,
   empty stderr, and no retry or fallback. No SCP, remote write, temporary file,
   old-runner execution, Cadence startup, OA/ADE/design/PDK access, or simulation.
5. Produce a new evidence version, never overwrite V1. Validate the closed
   identity and exactly eleven preimage records, exact-byte hashes, file type,
   owner, link count, mode, canonical containment, allowed absence, timestamp,
   package/collector provenance, and zero blockers. Any missing, changed, extra,
   ambiguous, or malformed field is a blocker, not an inferred value.
6. Review every proposed evidence field locally for credentials, license data,
   PDK/OA/ADE/netlist/schematic/layout/waveform content, host secrets, and
   unrestricted output before committing anything to this PUBLIC repository.
   A successful collection is not permission to publish unreviewed output.
7. After separate review of the new evidence hash, prepare a **new versioned
   recovery contract** that binds the new evidence, plan, package and deployer
   hashes. The existing recovery candidate pins V1 evidence, so it cannot be
   pointed at a new record by renaming or editing V1. Any required candidate
   change needs its own review, local tests, and exact authorization.
8. At any later execution gate, recheck current UTC, executor context, PUBLIC
   visibility, `deployment_enabled=false`, original and new claim lineage, and
   current fixed remote preflight under the separately approved operation.
   Evidence age is bounded by 24 hours at use. A dated diagnostic or V1
   preimage is not current preflight. An expired or uncertain new record routes
   back to a new versioned plan; it never triggers automatic recollection.

These gates are sequential. This document completes only the first planning
gate; it does not approve implementation, collection, recovery deployment, or
names-only discovery invocation.

## Acceptance criteria for this planning checkpoint

1. PR #45 merge commit is the exact latest fetched and remote `origin/main`.
2. Current UTC is at or after `2026-09-18T08:05:01Z`; V1 is marked expired.
3. The V1 evidence bytes, observation time, and hash are unchanged.
4. The consumed collection authorization lineage and claim are unchanged.
5. The failed deployment activation and six-field consumed claim are unchanged.
6. No historical approval, package, recovery plan, collector, or design evidence is edited.
7. The current collector's consumed claim prevents reuse of its old attempt.
8. New collection requires a separately reviewed versioned contract, implementation
   if needed, and exact single-use authority; none is instantiated here.
9. The new contract retains the eleven-asset allowlist, remote identity, shared
   operator lock, bounded output and time, and strict read-only transport.
10. New evidence must be versioned, closed-schema, locally screened before any
    PUBLIC commit, and independently hash-reviewed before recovery use.
11. A later recovery contract must bind the new evidence and implementation
    hashes; the V1-pinned candidate is not silently repointed.
12. No old evidence is treated as current identity, preimage, lock, process,
    snapshot, or design condition evidence.
13. PUBLIC and `deployment_enabled=false` remain unchanged.
14. Scientific VDD, VCM, load, source/state equivalence, and snapshot freshness
    remain unverified; conditional bias values are not promoted to baseline.
15. This checkpoint changes only this plan and `PROJECT_STATE.md`.
16. No Authorization, claim, lock, identity/binding read, SSH/SCP, remote
    collection/preflight/deployment, Cadence/SKILL, simulation, OA/ADE/design/PDK
    operation, main push/merge, or WP-15 work occurs.
17. Document checks, secret scan, relevant local security checks, clean diff,
    feature push, and remote commit-SHA verification pass before STOP.

## Local verification

Ruff and strict mypy passed for all 17 source files. The full suite in a clean
temporary Git export passed `384` tests, skipped eight remote integrations, and
reported 56 existing deprecation warnings. The live checkout's first test run
had two failures because a preserved, Git-ignored deployment authorization
artifact exists there and those tests require its absence; that artifact was
not touched or copied into the temporary export. The 368-file secret preflight,
18 dedicated security tests, strict dependency audit with no known
vulnerabilities, protected-file hash checks, unique state-key check, and
two-document scope check passed. No real integration was run.

## Next decision

Review this plan's feature commit. A later WP-14 run may draft the new
request-only collection contract and its acceptance criteria. It must not
activate the old collector or reuse its consumed claim. Remote recovery and
scientific baseline confirmation remain `BLOCKED`.
