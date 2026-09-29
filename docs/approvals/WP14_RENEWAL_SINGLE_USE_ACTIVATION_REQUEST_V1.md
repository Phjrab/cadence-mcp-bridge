# WP-14 renewal collector single-use activation request v1

## Status and scope

- Record kind: request for a separate approval, **not an Authorization or grant**.
- Status: BLOCKED; no activation, claim, lock or V2 evidence was created.
- Base: PR #49 merged reviewed head `9cab6ca75740cb6b656770c33802455216207cf4` as `af6c9a19fa0d0e6160d3939097c664d949f036b2` on 2026-09-29T01:48:41Z. That commit was the latest fetched and remote `origin/main` at this review.
- Repository visibility: PUBLIC. `remote/config/runner-lineage.json` retains `deployment_enabled=false`.
- This request is not stored at the collector's fixed private activation path. Merging it cannot authorize collection or any other operation. WP-14 remains blocked; WP-15 is not started.

The normative request contract is `docs/approvals/WP14_REMOTE_EVIDENCE_RENEWAL_COLLECTION_REQUEST_V1.md` (normalized-LF SHA-256 `747ec5d73372f7fc8149f773638a0be106d12698fa4a1b7a45306c49a2374f4a`). The inherited PUBLIC v2 package has digest `7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223`. The merged repository-side collector `scripts/collect-wp14-renewed-remote-preimages.py` has normalized-LF SHA-256 `d814d0da7ffc3890274ea24f1b9fc946bf861ec617860c6560cab320f08a3d89`; its reviewed implementation head was `4b90a7b405ccfe504d80cb352430a3bcacd78770` (PR #48). These public hashes were recalculated from the current tree. They establish source provenance, not live executor or remote readiness.

The V1 evidence expired at 2026-09-18T08:05:01Z. It remains immutable historical evidence, not an active preflight. Its normalized-LF digest is the already published `0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7`. The consumed predecessor collection/deployment claims, deployment activation and both existing lock lineages must be preserved without reset, deletion, reproduction, or reuse.

## Closed activation inputs to review separately

The collector requires exactly 19 fields. This table lists *sources and gates only*; it is deliberately not a populated JSON object, does not provide private values, and must not be copied to the executable activation location.

| Field(s) | Source or fixed constraint | Current review result |
| --- | --- | --- |
| `schema_version`, `record_kind`, `renewal_generation` | Collector-fixed schema 2, renewal record kind and `collection-renewal-v1`. | Public rule checked; no record created. |
| `status`, `remote_identity_preimage_collection_authorized` | Separately reviewed, exact single-use user approval; the collector accepts approved status and affirmative grant only in a future private record. | **Unapproved here.** |
| `contract_normalized_lf_sha256`, `package_normalized_lf_sha256` | Recalculate the two public documents above at the later gate. | Current tree checked; later exact-tree recheck required. |
| `collector_normalized_lf_sha256`, `repository_implementation_commit` | Recalculate collector bytes and bind the reviewed implementation commit with the exact blob in the then-current main. | Current tree checked; later exact-tree recheck required. |
| `predecessor_evidence_normalized_lf_sha256` | Preserved, expired V1 evidence digest; historical lineage only. | Published provenance identified; V1 must not be restamped. |
| `predecessor_collection_claim_sha256`, `predecessor_deployment_claim_sha256` | Future private local exact-byte review of both preserved, consumed claims under the fixed lock contract. | **Unverified. Neither private claim nor its digest was read or printed.** |
| `predecessor_deployment_authorization_normalized_lf_sha256` | Preserved consumed deployment-activation provenance, verified in a separately authorized private local review. | Public expected provenance identified; private artifact not opened here. |
| `executor_binding_rule`, `executor_binding` | Collector's fixed username/MachineGuid-based rule; future binding must be calculated and matched privately in the exact execution context. | Rule checked in source; **actual identity/binding unverified and undisclosed**. Prior SID/MachineGuid `LOCAL_RULE_READY` is not equivalent. |
| `authorization_id`, `not_before`, `expires_at` | Future fresh lowercase UUID and exact UTC interval; start must be active, end later than start and no more than 24 hours later. | **Unset.** No identifier or time window is inferred. |
| `max_uses` | Collector-fixed integer 1. | Public rule checked; no use granted or consumed. |

The table covers all 19 field names in the closed collector schema. An exact future activation must reject missing, extra or duplicate fields, wrong types, changed digests, wrong binding, invalid time, expired authority and an existing/partial renewal slot. Review of this request supplies none of the missing private inputs.

## Unresolved preconditions and fail-closed decision

Before any separate authorization, a specifically approved private local check would need to establish: exact current executor context and binding; both predecessor claim byte hashes and their closed six-field consumed lineage; unchanged deployment activation; both existing lock files and acquisition compatibility; no conflicting recovery authority; and absence of the fixed renewal activation, `collection-renewal-v1.json` claim slot and V2 evidence. This document performs **none** of those checks and makes no assertion about current private-file state. Missing, ambiguous, changed, reparse, active, or unreadable artifacts block the attempt; no cleanup, fallback name, altered UUID, or new checkout resets the single-use boundary.

Even after those checks, an explicit new authorization must bind the exact contract/package/collector/implementation provenance, private predecessor digests, current private executor binding, unique identifier, bounded UTC window and one use. It must be reviewed separately before one operator-only, read-only remote identity and eleven-asset preimage attempt could be considered. A future failure or uncertain outcome consumes that attempt and does not permit automatic retry. The collector's transport, 60-second deadline, 32,768-byte output cap, secret filtering and closed V2 schema remain mandatory. This request does not authorize SSH/SCP, collector or deployer execution, deployment, Cadence/SKILL, simulation, OA/ADE/design/PDK access, scientific baseline approval, or WP-15.

## Acceptance criteria for this request-only checkpoint

1. PR #49's reviewed head, merge commit, latest fetched and remote main agree; PUBLIC visibility and `deployment_enabled=false` are unchanged.
2. The current contract, package and collector normalized-LF digests match their published values; the implementation commit is in main with the reviewed collector.
3. Exactly 19 closed activation fields are accounted for by source and constraint, without creating an activation or disclosing private claim, executor identity, binding, UUID or current lock state.
4. V1 evidence and all predecessor claims, activation, lock lineages and earlier decision/evidence records are unchanged. No renewal activation, claim, lock or V2 evidence is created.
5. Every unknown remains explicitly unverified; separate exact single-use approval and private local preflight are required. PUBLIC publication receives a semantic sensitive-data check, not merely a generic secret scan.
6. Only this request and `PROJECT_STATE.md` are changed on a feature branch. Documentation/security checks and remote feature-HEAD verification pass before STOP; main is neither pushed nor merged.
