# WP-14 remote evidence renewal collection request v1

## Record and authority

- Contract ID: `WP14_REMOTE_EVIDENCE_RENEWAL_COLLECTION_REQUEST`.
- Version: `1`; record kind: `renewal_collection_request_not_grant`.
- Prepared on: `2026-09-28`.
- Document status: `READY_FOR_REVIEW`; execution status: `BLOCKED`.
- Baseline: PR #46, reviewed head `2fef43d003b5ecaccf9f2b57aee56e42d02f7f53`,
  merge/latest fetched and remote main `9f2172a5a2ba189afb39ba3751528928e168e06a`.
- Repository: `Phjrab/cadence-mcp-bridge`, PUBLIC; `deployment_enabled=false`.

This Markdown request completes the next documentation gate of
`docs/WP14_FAIL_CLOSED_EVIDENCE_RENEWAL_PLAN_V1.md`. All authority granted by this
artifact is false: implementation, identity/binding capture, Authorization/claim/lock
creation, SSH/SCP, collection, deployment/preflight, Cadence/SKILL/discovery,
simulation, OA/ADE/design/PDK access, role binding and scientific approval.
Review or merge does not activate any of those operations. WP-14 remains blocked;
WP-15 does not start. No existing request, plan, evidence or executable is replaced.

The contract digest is SHA-256 of the entire UTF-8 document, replacing CRLF and
bare CR with LF, without trimming or adding characters. The document has no BOM.
Its final digest is recorded in `PROJECT_STATE.md` and the completion report, not
inside this document (which would create a self-referential digest). A future
implementation and activation must bind that exact reviewed digest.

## Immutable provenance

All digests in this table are normalized-LF SHA-256. These are repository
provenance, not fresh remote observations or permission to execute old programs.

| Existing artifact | Digest |
| --- | --- |
| `docs/WP14_FAIL_CLOSED_EVIDENCE_RENEWAL_PLAN_V1.md` | `305e8a4eed2cbabb4160ebe65456b7f0ae694eb02d4a07d800d4cfc12029a432` |
| `docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json` | `7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223` |
| `docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_SINGLE_USE_APPROVAL_PACKAGE_V2.json` | `9b1ed3e2fc4a9ba5c05e5475bca51949a6eba0cbdcbbd47d3c54f549d576bd0f` |
| `docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json` | `96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431` |
| `scripts/collect-wp14-remote-preimages.py` | `b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c` |
| `scripts/deploy-wp14-narrow.ps1` | `3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc` |
| `scripts/deploy-wp14-recovery.ps1` | `e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374` |
| `docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V1.json` | `0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7` |

V1 was observed at `2026-09-17T08:05:01Z` and expired at
`2026-09-18T08:05:01Z`. Preserve its exact bytes, timestamp, digest and historical
seven-present/four-absent result. Those counts do not predict a new observation.
Preserve the consumed collection activation lineage digest
`631d6dff580edb449cac6b4d342930428bd49bc7fd3337053c9932737a581a20`.
The original collection activation was removed after its approved use; do not
recreate it. Preserve the failed deployment activation with digest
`095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`
and its six-field consumed claim, including
`consumed_at=2026-09-17T08:20:37.8800486+00:00`. Preserve all earlier V1-V4
design evidence, approvals, recovery files and historical state entries.

## Fixed read-only observation boundary

The proposed future collector is argument-free, operator-only and not an MCP
tool. It accepts no caller path, command, environment override, design identifier,
property or value. Its compiled target remains alias `cadence-vm`, hostname
`cadence`, user `buet`, and canonical root `/home/buet/cds_work/.cadence_mcp`.
Use only Windows System32 OpenSSH, BatchMode, strict host-key verification and
the reviewed fixed identity/preimage command. No old-runner execution is needed.

Exactly these ordered eleven targets are inherited from the PUBLIC v2 package.
The repository path is `remote/` followed by the relative path in the table;
the remote destination is the fixed root followed by that same relative path.

| Index | Relative path | Required presence |
| --- | --- | --- |
| 0 | `bin/cadence-runner` | file |
| 1 | `lib/runner-common.sh` | file |
| 2 | `lib/run-ade-profile-introspection.sh` | file or absent |
| 3 | `lib/run-wp14-role-discovery.sh` | file or absent |
| 4 | `py26/actual_profile_audit.py` | file or absent |
| 5 | `py26/ade_profile_introspection.py` | file or absent |
| 6 | `py26/wp14_role_discovery.py` | file or absent |
| 7 | `discovery/ade-profile-introspection.il` | file or absent |
| 8 | `discovery/wp14-role-discovery.il` | file or absent |
| 9 | `config/runner-lineage.json` | file or absent |
| 10 | `profiles/actual-differential-amplifier-tb2-transient/profile.json` | file or absent |

Present files must be regular, owned by `buet`, have one hard link, mode `600`
or `700`, no symlink/reparse escape, and canonical containment below the fixed
root. SHA-256 covers exact remote bytes, never normalized text. Allowed absence
must be proved at the exact destination; dangling links are not absence. Reject
ambiguous parent containment. File bytes, unrelated directory listings, environment,
license, credential, PDK/OA/ADE/netlist/schematic/layout/waveform content and raw
logs cannot be emitted. Hashing a managed file does not authorize executing it.

One authorized attempt permits one SSH process, maximum parallelism one, a shared
60-second monotonic transport deadline and at most 32,768 combined stdout/stderr
bytes. Enforce these while the process runs. Require strict UTF-8, empty stderr,
exit zero, exact identity/record ordering/terminator and bounded parsing. Expiry
is checked before and during transport. Timeout, launch failure, partial output,
unknown outcome or any failed check ends the attempt; no retry, fallback,
cleanup, SCP, upload, snapshot, remote temporary file or remote write is allowed.

## Preserved claims and shared lock lineage

`LOCAL_APP_DATA` below denotes the existing Windows known-folder location;
it is not a new path, caller argument or environment override. Do not print its
resolved user path or derive a ledger from a repository checkout.

The existing collector uses:

- ledger `LOCAL_APP_DATA/CadenceMcpBridge/wp14-preimage-evidence`;
- lock `operation.lock` in that ledger;
- consumed slot `attempt-1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb.json`.

The existing deployment and recovery candidates share:

- ledger `LOCAL_APP_DATA/CadenceMcpBridge/wp14-narrow`;
- common lock `operation.lock` in that ledger;
- deployment slot `attempt-7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87.json`;
- separately reserved recovery slot `recovery-v1.json`.

These are two existing lock files, not one already-proven cross-operation lock.
Current source proves their names and locking code; this documentation run does
not claim to test live contention. The renewed collector must preserve both
domains and, under separately approved implementation, acquire the deployment
common lock first and the collection lock second, nonblocking, with semantics
compatible with their current Windows holders. Hold both through predecessor
verification, durable consumption, transport, validation and bounded output;
release handles in reverse order. Never delete, rename, truncate, reset or
replace either lock. Missing/unverifiable/reparse ledgers or locks block the new
operation; this contract grants no ledger repair or new common lock creation.

The old collector's package-wide claim key intentionally survived the v1-to-v2
public-policy migration. A new UUID, new checkout, edited package, timestamp,
activation filename or package version cannot make that consumed slot reusable.
It also refuses a present deployment Authorization V2. The preserved consumed
deployment activation is evidence, so deleting it to satisfy that old guard is
forbidden. The old collector is ineligible for renewal and is not invoked.

### Proposed renewal namespace (names only; no artifacts created)

- Fixed logical generation: `collection-renewal-v1`.
- Proposed private activation: `docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json`.
- Proposed durable slot: `collection-renewal-v1.json` in the existing collection ledger.
- Proposed published evidence: `docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V2.json`.

These proposed names require review of this contract and of their enforcement
before use. They reserve one renewal generation, not an automatic series of
attempts. The slot is independent of contract/collector hash, authorization UUID,
branch and checkout. A revised request or implementation must still reject any
existing slot, including empty/partial files. Do not select another name on
collision. V2 evidence must also be absent before a future attempt; never overwrite
or silently fall back to V3. This request is stored at none of those paths.

Within both locks, verify the bounded closed six-field predecessor claims and
their exact private review digests before consuming a renewal. Collection fields
are `state`, `authorization_id`, `authorization_sha256`, `package_sha256`,
`collector_sha256`, `consumed_at`; deployment substitutes `deployer_sha256`.
Require `consumed_before_transport`, the pinned historical activation/package/
implementation bindings above, scalar types, valid original timestamps and
unchanged bytes. No identifier or timestamp is reconstructed or inferred. Retain
the deployment activation and check its known digest without outputting contents.
Any missing, malformed, extra, duplicate, oversized (over 4,096 bytes) or mismatched
predecessor is a blocker. No old claim is written or re-consumed. An existing
recovery claim blocks this proposed renewal pending review, without modification.

Only after a separate exact activation approval may the new slot use exclusive
create-new, durable write and flush before process launch. Record the contract,
collector and activation hashes, predecessor claim hashes, generation and original
consumption timestamp privately. Failure during write/flush/launch, uncertain
completion, expired authority or failed transport leaves the slot consumed;
it must not be cleaned up to permit retry. Verify predecessor bytes again after
the operation and keep both old and new records for audit.

## Future private activation requirements, currently unset

The later reviewed implementation must enforce this closed field set; this is
a schema description, not a populated Authorization or sample ready for execution:

| Field | Required source or constraint |
| --- | --- |
| `schema_version` | Renewal schema 2, distinct from the legacy collection schema 1. |
| `record_kind` | Fixed `explicit_remote_identity_preimage_renewal_authorization`. |
| `status` | An approved status only in a separately granted activation; this request grants none. |
| `renewal_generation` | Fixed `collection-renewal-v1`. |
| `contract_normalized_lf_sha256` | Exact reviewed digest of this request. |
| `package_normalized_lf_sha256` | Inherited v2 package digest `7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223`. |
| `collector_normalized_lf_sha256` | UNSET until a new implementation is reviewed; the old digest is not substituted. |
| `repository_implementation_commit` | UNSET; reviewed implementation commit present in current main with the exact collector blob. No self-commit hash is embedded into its own source. |
| `predecessor_evidence_normalized_lf_sha256` | Immutable V1 digest above, explicitly historical. |
| `predecessor_collection_claim_sha256` | UNSET here; exact-byte digest from separately reviewed private local lineage. |
| `predecessor_deployment_claim_sha256` | UNSET here; exact-byte digest from separately reviewed private local lineage. |
| `predecessor_deployment_authorization_normalized_lf_sha256` | Preserved `095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`. |
| `executor_binding_rule` | `windows_username_pipe_machineguid_sha256_v1`, matching the collector's existing rule. |
| `executor_binding` | UNSET; approved local execution context, never inferred or published. |
| `authorization_id` | UNSET; later separately approved fresh lowercase UUID. |
| `not_before` | UNSET; later exact UTC activation start. |
| `expires_at` | UNSET; later UTC end, strictly after start, interval at most 24 hours. |
| `max_uses` | Exactly integer 1. |
| `remote_identity_preimage_collection_authorized` | True only in that future explicit grant, never supplied by this request. |

Reject extra/duplicate keys, wrong scalar types, reparse paths and records over
16,384 bytes. The known local `LOCAL_RULE_READY` result used the recovery
SID/MachineGuid rule; it is neither this collector's username/MachineGuid binding
nor current remote readiness. No identity, UUID, interval, new collector digest
or executable activation is supplied here. The separate renewal implementation
must recognize only the exact consumed deployment activation plus matching claim
as preserved lineage; any other active/mismatched deployment or recovery authority
blocks collection. It must never call either deployer.

## Proposed evidence v2 and publication review

Keep V1 unchanged. New evidence has schema version 2 and record kind
`wp14_renewed_remote_identity_preimage_evidence`, with exactly these top-level keys:
`schema_version`, `record_kind`, `renewal_contract_normalized_lf_sha256`,
`source_package_normalized_lf_sha256`, `collector_normalized_lf_sha256`,
`repository_implementation_commit`, `predecessor_evidence_normalized_lf_sha256`,
`collection_started_at`, `observed_at`, `remote_identity`, `preimages`, `blockers`.

Identity keys remain exactly `hostname`, `user`, `root`, `resolved_root`,
`root_is_directory`, `root_is_symlink`, `verified`. Each of exactly eleven ordered
preimages has only `path`, `presence`, `sha256`, `mode`, `owner`, `file_type`,
`hard_link_count`, `is_symlink`, `resolved_under_root`. Use inherited v2 types and
absence semantics: absent hash/mode/owner/type/link count are null; symlink is
false and containment true. Successful evidence has an empty blocker list.
Failures return only bounded allowlisted error codes, never partial success,
raw stderr, discovered paths or file contents. Cap JSON at 32,768 bytes and
nesting depth eight; reject duplicates and any unapproved fields or values.

Capture both UTC timestamps during the actual future attempt. Require start
not after observation, observation not in the future and the fixed 60-second
monotonic execution bound. At later use require age from the earlier collection
start strictly less than 24 hours; at the boundary it is expired. Never restamp an
old result or automatically recollect it. Historical differences from V1 are
reported for review; neither V1 preimages nor repository candidate hashes are
guessed as current remote bytes. Drift does not authorize replacement or recovery.

Review every field locally for credentials, MachineGuid/raw identity/binding,
license data, environment values and protected circuit/PDK/OA/ADE content before
any PUBLIC commit. Public output excludes the private activation and claim
contents/digests, personal paths, executor binding and authorization UUID. Only
the fixed target labels, bounded preimage metadata and reviewed provenance above
are eligible for publication. A secret scan alone is not semantic field review.
New evidence remains insufficient for deployment until its exact hash is reviewed
and a separately versioned recovery contract binds it. The V1-pinned recovery
candidate is not repointed. VDD, VCM, load, semantic source/state equivalence and
snapshot freshness remain unverified; bias selection remains conditional.

## Review gates and acceptance criteria

This run may validate documents and public metadata, update PROJECT_STATE,
commit/push only this feature, verify the remote SHA, then STOP. It does not
implement or exercise the proposed collector. The next concrete gate is review
and integration of this request, followed by separately scoped repository-only
implementation and synthetic/fake-transport tests. A final collector digest,
private predecessor/identity bindings and exact single-use activation require
review before one later remote attempt. Recovery and discovery remain later gates.

### Current document checkpoint

1. PR #46 approved head/merge and latest fetched/remote main agree; PUBLIC is verified.
2. This new request and PROJECT_STATE are the only changed files; no old artifact is overwritten.
3. Every immutable provenance digest matches; old evidence timestamps and bytes are unchanged.
4. Consumed collection/deployment activation/claim lineage and both common lock files retain their pre-run existence and bytes; no operational object is created.
5. Exactly eleven ordered inherited assets, presence rules and fixed target identity match v2.
6. The original consumed package-wide attempt is explicitly ineligible; UUID/hash/checkout/version changes do not reset it.
7. The two existing lock domains and proposed acquisition order are explicit; no new lock namespace is substituted.
8. A distinct proposed renewal activation/slot/evidence namespace is defined as names only, with collision rejection and one total attempt.
9. Future private activation fields remain unpopulated; this request has no executable authority.
10. Time/output/concurrency bounds, closed evidence schema, PUBLIC field review and no retry/fallback/cleanup are retained.
11. The future implementation/test and exact-execution gates are explicit; no current collector, deployer or identity checker is run.
12. PROJECT_STATE records PR #46, this digest and pending review; WP-14 remains blocked, deployment disabled and WP-15 unstarted.
13. Document/metadata/hash/preservation checks, local security tests, secret scan and diff whitespace checks pass before commit.
14. Conventional commit and feature-only push are verified against remote SHA; no main push or merge occurs.

### Required tests at the separate implementation gate

15. Temporary synthetic fixtures alone prove one accepted activation, both locks held, immutable predecessor verification and durable new-slot consumption before the sole fake transport.
16. Both predecessor claims and the consumed deployment activation are byte-identical after success and every failure. Wrong/missing/partial/extra/duplicate lineage rejects before consumption or transport.
17. An existing/empty/partial renewal slot, changed UUID/contract hash/version/checkout, concurrent original collection or deployment/recovery, lock absence, reparse path or collision never grants a second attempt. Use the actual compatible Windows lock primitives on temporary fixtures.
18. Test crash/flush/launch failure, timeout during streaming, stdout/stderr flood, nonempty stderr, invalid UTF-8, malformed/count/ordering/identity/type/hash/mode/owner/link/containment output and expiry. Every consumed failure remains consumed with no additional transport or cleanup.
19. Reject the old activation, unreviewed collector/commit, wrong executor rule, other active deployment/recovery authority and protected output. No production test bypass, arbitrary shell/SKILL or MCP interface is introduced.
20. New evidence cannot overwrite V1/V2, contain activation/binding/claim data, acquire scientific authority or silently satisfy the old recovery candidate. No live identity or SSH/SCP is used by local tests.

Criteria 15-20 are future acceptance requirements, not tests claimed to have run
in this documentation checkpoint. Local documentation success does not change the
expired-evidence or unapproved-execution status.
